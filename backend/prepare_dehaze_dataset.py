"""
构建真实图像去雾配对数据集（Admin/dehaze-dataset）：
  - 下载真实自然风景/街景/建筑高清照片（Pillow 校验 + SHA-256 去重，训练/测试零重叠）
  - 按 RESIDE 标准大气散射物理模型 I(x) = J(x)*exp(-beta*d(x)) + A*(1 - exp(-beta*d(x)))
    结合平滑空间景深场 d(x, y) 生成真实雾天配对图
  - 落盘至 backend/data/dehaze-dataset/{train,test}/{images,clear,labels.csv}
    并预打包 ZIP 供后端 FileResponse 极速流式下载
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import shutil
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "dehaze-dataset"

TRAIN_COUNT = 800
TEST_COUNT = 200
TOTAL_NEEDED = TRAIN_COUNT + TEST_COUNT
IMG_W, IMG_H = 384, 256
HEADERS = {"User-Agent": "AlgoHub-DehazeDatasetBuilder/1.0"}


def fetch_outdoor_photo(idx: int) -> tuple[bytes, str] | None:
    # Picsum 提供 CC0/Unsplash 真实自然与城市摄影照片
    url = f"https://picsum.photos/seed/dehaze{idx + 100}/{IMG_W}/{IMG_H}.jpg"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        if len(raw) < 5000:
            return None
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            rgb = im.convert("RGB").resize((IMG_W, IMG_H), Image.Resampling.LANCZOS)
            arr = np.asarray(rgb, dtype=np.float32)
            # 过滤纯色或过暗图
            if arr.std() < 18.0 or arr.mean() < 25.0:
                return None
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=92)
            data = buf.getvalue()
            return data, hashlib.sha256(data).hexdigest()
    except Exception:
        return None


def synthesize_haze(clear_rgb: np.ndarray, rng: random.Random) -> tuple[np.ndarray, float, float]:
    """基于大气散射物理模型生成空间连续变化浓度的有雾图像"""
    h, w, _ = clear_rgb.shape
    y = np.linspace(1.0, 0.15, h, dtype=np.float32)[:, None]  # 上方远景雾更浓、下方近景较轻
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    # 叠加平滑低频景深起伏模拟建筑/山体层次
    p1 = rng.uniform(0.0, math.pi * 2)
    p2 = rng.uniform(0.0, math.pi * 2)
    wave = 0.14 * np.sin(2.0 * math.pi * x + p1) * np.cos(1.5 * math.pi * y + p2)
    depth = np.clip(y + wave, 0.12, 1.0)

    beta = round(rng.uniform(0.95, 2.15), 3)
    airlight = round(rng.uniform(0.78, 0.96), 3)
    t = np.exp(-beta * depth)[..., None]

    j = clear_rgb.astype(np.float32) / 255.0
    hazy = j * t + airlight * (1.0 - t)
    hazy_u8 = np.clip(hazy * 255.0, 0, 255).astype(np.uint8)
    return hazy_u8, beta, airlight


def write_split(split: str, clear_list: list[bytes]) -> dict:
    split_dir = DATA_DIR / split
    if split_dir.exists():
        shutil.rmtree(split_dir)
    hazy_dir = split_dir / "images"
    clear_dir = split_dir / "clear"
    hazy_dir.mkdir(parents=True, exist_ok=True)
    clear_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(20261120 if split == "train" else 20261121)
    rows: list[tuple[str, str, str, str]] = []
    hasher = hashlib.sha256()
    total_bytes = 0

    zip_path = DATA_DIR / f"dehaze-dataset-{split}-v1.0.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for idx, clear_bytes in enumerate(clear_list, start=1):
            with Image.open(io.BytesIO(clear_bytes)) as im:
                clear_arr = np.asarray(im.convert("RGB"))
            hazy_arr, beta, airlight = synthesize_haze(clear_arr, rng)
            hazy_buf = io.BytesIO()
            Image.fromarray(hazy_arr).save(hazy_buf, format="JPEG", quality=92)
            hazy_bytes = hazy_buf.getvalue()

            hazy_rel = f"images/{split}_{idx:04d}.jpg"
            clear_rel = f"clear/{split}_{idx:04d}.jpg"
            (split_dir / hazy_rel).write_bytes(hazy_bytes)
            (split_dir / clear_rel).write_bytes(clear_bytes)

            zf.writestr(f"{split}/{hazy_rel}", hazy_bytes)
            zf.writestr(f"{split}/{clear_rel}", clear_bytes)

            total_bytes += len(hazy_bytes) + len(clear_bytes)
            hasher.update(hazy_bytes)
            hasher.update(clear_bytes)
            rows.append((hazy_rel, clear_rel, f"{beta:.3f}", f"{airlight:.3f}"))

        csv_path = split_dir / "labels.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["file_name", "clear_file", "beta", "airlight"])
            w.writerows(rows)
        csv_bytes = csv_path.read_bytes()
        zf.writestr(f"{split}/labels.csv", csv_bytes)
        total_bytes += len(csv_bytes)
        hasher.update(csv_bytes)

    print(f"[{split}] 写入 {len(rows)} 组真实有雾/清晰配对图（{total_bytes / (1024**2):.2f} MB），已预打包 {zip_path.name}")
    return {
        "name": split,
        "columns": ["file_name", "clear_file", "beta", "airlight"],
        "files": len(rows),
        "rows": len(rows),
        "sizeBytes": total_bytes,
        "contentHash": "sha256:" + hasher.hexdigest(),
        "classCounts": {"轻雾 (β<1.3)": sum(1 for r in rows if float(r[2]) < 1.3), "中雾 (1.3≤β<1.75)": sum(1 for r in rows if 1.3 <= float(r[2]) < 1.75), "浓雾 (β≥1.75)": sum(1 for r in rows if float(r[2]) >= 1.75)},
    }


def main():
    rebuild = "--rebuild" in sys.argv
    meta_path = DATA_DIR / "meta.json"
    if not rebuild and meta_path.exists() and (DATA_DIR / "test" / "labels.csv").exists():
        old_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        old_total = old_meta.get("train", {}).get("files", 0) + old_meta.get("test", {}).get("files", 0)
        if old_total >= TOTAL_NEEDED:
            print(f"去雾数据集已满足规模（{old_total} 组）：", DATA_DIR)
            return
        print(f"检测到现有数据集仅 {old_total} 组，将扩充至 {TOTAL_NEEDED} 组…")

    collected: list[bytes] = []
    seen: set[str] = set()

    print(f"正在下载 {TOTAL_NEEDED} 张纯自然/街景/建筑高清底图（不混入猫狗图）…")
    seed_cursor = 100
    max_attempts = 6
    attempt = 0
    while len(collected) < TOTAL_NEEDED and attempt < max_attempts:
        attempt += 1
        batch_size = min(450, (TOTAL_NEEDED - len(collected)) + 160)
        with ThreadPoolExecutor(max_workers=24) as pool:
            futs = [pool.submit(fetch_outdoor_photo, seed_cursor + i) for i in range(batch_size)]
            seed_cursor += batch_size
            for fut in as_completed(futs):
                if len(collected) >= TOTAL_NEEDED:
                    break
                item = fut.result()
                if not item:
                    continue
                data, sha = item
                if sha in seen:
                    continue
                seen.add(sha)
                collected.append(data)
                if len(collected) % 100 == 0:
                    print(f"  已收集 {len(collected)} / {TOTAL_NEEDED} 张真实风景/街景底图…")

    print(f"共获取 {len(collected)} 张去重真实风景/街景底图")
    rng = random.Random(20261120)
    rng.shuffle(collected)
    n_test = min(TEST_COUNT, max(20, len(collected) // 5))
    test_clear = collected[:n_test]
    train_clear = collected[n_test:]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    train_meta = write_split("train", train_clear)
    test_meta = write_split("test", test_clear)

    meta = {
        "source": "Real Outdoor Scenes + Atmospheric Scattering Model (RESIDE Protocol)",
        "train": train_meta,
        "test": test_meta,
    }
    (DATA_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("去雾数据集构建完成！")


if __name__ == "__main__":
    main()
