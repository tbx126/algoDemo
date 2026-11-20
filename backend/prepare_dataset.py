"""
从 Microsoft 官方下载完整的 Dogs vs. Cats 数据集（kagglecatsanddogs_5340.zip，约 25,000 张真实猫狗图），
逐张校验图片完整性、按 SHA-256 去重后按 80% / 20% 切分为训练集与测试集：
  backend/data/cat-dog-dataset/
    train/images/  + train/labels.csv  (file_name,label)
    test/images/   + test/labels.csv   (file_name,label)
    cat-dog-dataset-train-v1.0.zip     (预打包，供后端 FileResponse 极速流式下载)
    cat-dog-dataset-test-v1.0.zip
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import shutil
import subprocess
import warnings
import zipfile
from pathlib import Path
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "cat-dog-dataset"
RAW_ZIP = ROOT / "data" / "kagglecatsanddogs_5340.zip"
MS_URL = "https://download.microsoft.com/download/3/E/1/3E1C3F21-ECDB-4869-8368-6DEBA77B919F/kagglecatsanddogs_5340.zip"

TRAIN_RATIO = 0.8


def download_ms_zip() -> None:
    RAW_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if RAW_ZIP.exists() and RAW_ZIP.stat().st_size > 800_000_000:
        print(f"官方压缩包已存在：{RAW_ZIP} ({RAW_ZIP.stat().st_size / (1024**2):.1f} MB)")
        return
    print(f"正在从 Microsoft 官方下载 Dogs vs. Cats (~787 MB)...")
    cmd = [
        "curl.exe",
        "-L",
        "-C",
        "-",
        "--fail",
        "--retry",
        "10",
        "--retry-all-errors",
        "--retry-delay",
        "3",
        "-o",
        str(RAW_ZIP),
        MS_URL,
    ]
    for attempt in range(1, 8):
        r = subprocess.run(cmd)
        if r.returncode == 0 and RAW_ZIP.exists() and RAW_ZIP.stat().st_size > 800_000_000:
            break
        print(f"下载中断（退出码 {r.returncode}），第 {attempt} 次断点续传…", flush=True)
    else:
        raise RuntimeError("多次续传后仍未能完整下载 kagglecatsanddogs_5340.zip")
    print(f"下载完成：{RAW_ZIP.stat().st_size / (1024**2):.1f} MB")


def validate_jpeg(raw: bytes) -> bool:
    if len(raw) < 1024:
        return False
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.verify()
        with Image.open(io.BytesIO(raw)) as img:
            if img.width < 16 or img.height < 16:
                return False
            img.convert("RGB")
        return True
    except Exception:
        return False


def write_split(split: str, zf_in: zipfile.ZipFile, entries: list[tuple[str, str]]) -> dict:
    split_dir = DATA_DIR / split
    img_dir = split_dir / "images"
    if split_dir.exists():
        shutil.rmtree(split_dir)
    img_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(20261120 if split == "train" else 20261121)
    rng.shuffle(entries)

    rows: list[tuple[str, str]] = []
    hasher = hashlib.sha256()
    total_bytes = 0
    class_counts: dict[str, int] = {"猫": 0, "狗": 0}

    zip_out_path = DATA_DIR / f"cat-dog-dataset-{split}-v1.0.zip"
    with zipfile.ZipFile(zip_out_path, "w", compression=zipfile.ZIP_STORED) as zf_out:
        for idx, (label, member_name) in enumerate(entries, start=1):
            raw = zf_in.read(member_name)
            prefix = "cat" if label == "猫" else "dog"
            rel_name = f"images/{split}_{prefix}_{idx:05d}.jpg"
            (split_dir / rel_name).write_bytes(raw)
            zf_out.writestr(f"{split}/{rel_name}", raw)
            total_bytes += len(raw)
            hasher.update(raw)
            rows.append((rel_name, label))
            class_counts[label] = class_counts.get(label, 0) + 1

        csv_path = split_dir / "labels.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["file_name", "label"])
            w.writerows(rows)
        csv_bytes = csv_path.read_bytes()
        zf_out.writestr(f"{split}/labels.csv", csv_bytes)
        total_bytes += len(csv_bytes)
        hasher.update(csv_bytes)

    print(
        f"[{split}] 写入 {len(rows)} 张真实图片（猫 {class_counts['猫']} / 狗 {class_counts['狗']}），"
        f"{total_bytes / (1024**2):.1f} MB，已预打包 {zip_out_path.name}"
    )
    return {
        "name": split,
        "columns": ["file_name", "label"],
        "files": len(rows),
        "rows": len(rows),
        "sizeBytes": total_bytes,
        "contentHash": "sha256:" + hasher.hexdigest(),
        "classCounts": class_counts,
    }


def main():
    download_ms_zip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("正在校验 25,000 张图片并按 SHA-256 去重…")
    cats: list[str] = []
    dogs: list[str] = []
    seen_sha: set[str] = set()
    corrupted = 0
    duplicates = 0

    with zipfile.ZipFile(RAW_ZIP, "r") as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".jpg") and ("PetImages/Cat/" in m or "PetImages/Dog/" in m)]
        members.sort()
        for i, m in enumerate(members, start=1):
            raw = zf.read(m)
            if not validate_jpeg(raw):
                corrupted += 1
                continue
            sha = hashlib.sha256(raw).hexdigest()
            if sha in seen_sha:
                duplicates += 1
                continue
            seen_sha.add(sha)
            if "PetImages/Cat/" in m:
                cats.append(m)
            else:
                dogs.append(m)
            if i % 5000 == 0:
                print(f"  已扫描 {i}/{len(members)}（有效猫 {len(cats)}，有效狗 {len(dogs)}，损坏 {corrupted}，重复 {duplicates}）")

        print(f"扫描完成：有效猫 {len(cats)}，有效狗 {len(dogs)}，跳过损坏 {corrupted}，去重 {duplicates}")

        rng = random.Random(20261120)
        rng.shuffle(cats)
        rng.shuffle(dogs)

        n_cat_train = int(len(cats) * TRAIN_RATIO)
        n_dog_train = int(len(dogs) * TRAIN_RATIO)

        train_entries = [("猫", m) for m in cats[:n_cat_train]] + [("狗", m) for m in dogs[:n_dog_train]]
        test_entries = [("猫", m) for m in cats[n_cat_train:]] + [("狗", m) for m in dogs[n_dog_train:]]

        train_meta = write_split("train", zf, train_entries)
        test_meta = write_split("test", zf, test_entries)

    meta = {
        "source": "Microsoft Dogs vs. Cats (kagglecatsanddogs_5340.zip)",
        "train": train_meta,
        "test": test_meta,
    }
    (DATA_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    # 清理原始大压缩包释放磁盘空间
    try:
        RAW_ZIP.unlink()
    except OSError:
        pass
    print("Microsoft Dogs vs. Cats 完整数据集构建完成！")


if __name__ == "__main__":
    main()
