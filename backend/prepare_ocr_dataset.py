"""
构建真实大规模 OCR 文本识别数据集（Admin/sroie-ocr-dataset）：
  - 数据来源：官方 ICDAR-2019 SROIE 竞赛真实扫描票据集（626 张高分辨率扫描票据 + 33,000+ 人工精标文本行）
  - 按票据维度 80% / 20% 切分训练与测试集（零票据重叠、无数据泄漏）
  - 逐行按人工标注四点坐标裁剪真实文本行图片（带 2px 上下文留白），过滤极小噪点与空文本，按图片 SHA-256 严格去重
  - 输出：
      backend/data/sroie-ocr-dataset/{train,test}/images/*.jpg
      backend/data/sroie-ocr-dataset/{train,test}/labels.csv  (file_name,text,category,source_receipt)
      backend/data/sroie-ocr-dataset/sroie-ocr-dataset-{train,test}-v1.0.zip
      backend/data/sroie-ocr-dataset/meta.json
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "sroie-ocr-dataset"
REPO_ZIP_URL = "https://github.com/zzzDavid/ICDAR-2019-SROIE/archive/refs/heads/master.zip"

RE_NUMERIC = re.compile(r"^[\d\s.,:%$+\-*/()RMrm]+$")
RE_DATE_OR_CODE = re.compile(r"(\d{2,4}[-/.]\d{1,2}[-/.]\d{1,4})|(\d{1,2}:\d{2})|(^[A-Z0-9\-/#]{4,}$)")


def classify_text(text: str) -> str:
    t = text.strip()
    if RE_NUMERIC.match(t) and any(ch.isdigit() for ch in t):
        return "数字与金额"
    if RE_DATE_OR_CODE.search(t) and any(ch.isdigit() for ch in t):
        return "日期与编号"
    return "文本与抬头"


def download_repo_zip(dest: Path) -> None:
    print(f"正在从 GitHub 下载 ICDAR-2019 SROIE 原始票据与标注包：\n  {REPO_ZIP_URL}")
    subprocess.check_call(
        ["curl.exe", "-L", "--fail", "--retry", "3", "--connect-timeout", "20", "-o", str(dest), REPO_ZIP_URL],
    )
    print(f"下载完成：{dest.stat().st_size / (1024 * 1024):.2f} MB")


def parse_box_csv(csv_path: Path) -> list[tuple[int, int, int, int, str]]:
    items: list[tuple[int, int, int, int, str]] = []
    text_raw = csv_path.read_text(encoding="utf-8", errors="ignore")
    for line in text_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",", 8)
        if len(parts) < 9:
            continue
        try:
            coords = [int(float(parts[i])) for i in range(8)]
        except ValueError:
            continue
        gt = parts[8].strip()
        if not gt or gt == "###":
            continue
        xs = coords[0::2]
        ys = coords[1::2]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        if (x2 - x1) < 14 or (y2 - y1) < 9:
            continue
        items.append((x1, y1, x2, y2, gt))
    return items


def build_split(
    split: str,
    receipt_pairs: list[tuple[str, Path, Path]],
    seen_hashes: set[str],
) -> dict:
    split_dir = DATA_DIR / split
    if split_dir.exists():
        shutil.rmtree(split_dir)
    img_dir = split_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str, str, str]] = []
    class_counts: dict[str, int] = {"数字与金额": 0, "日期与编号": 0, "文本与抬头": 0}
    total_bytes = 0
    hasher = hashlib.sha256()

    zip_path = DATA_DIR / f"sroie-ocr-dataset-{split}-v1.0.zip"
    idx = 0

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for receipt_id, img_path, box_path in receipt_pairs:
            boxes = parse_box_csv(box_path)
            if not boxes:
                continue
            try:
                with Image.open(img_path) as im:
                    rgb = im.convert("RGB")
                    W, H = rgb.size
                    for x1, y1, x2, y2, gt in boxes:
                        pad = 2
                        cx1 = max(0, x1 - pad)
                        cy1 = max(0, y1 - pad)
                        cx2 = min(W, x2 + pad)
                        cy2 = min(H, y2 + pad)
                        if (cx2 - cx1) < 12 or (cy2 - cy1) < 8:
                            continue
                        crop = rgb.crop((cx1, cy1, cx2, cy2))
                        buf = io.BytesIO()
                        crop.save(buf, format="JPEG", quality=92)
                        raw = buf.getvalue()
                        sha = hashlib.sha256(raw).hexdigest()
                        if sha in seen_hashes:
                            continue
                        seen_hashes.add(sha)

                        idx += 1
                        rel = f"images/{split}_{idx:05d}.jpg"
                        (split_dir / rel).write_bytes(raw)
                        zf.writestr(f"{split}/{rel}", raw)

                        cat = classify_text(gt)
                        class_counts[cat] = class_counts.get(cat, 0) + 1
                        rows.append((rel, gt, cat, f"{receipt_id}.jpg"))
                        total_bytes += len(raw)
                        hasher.update(raw)
            except Exception:
                continue

        csv_path = split_dir / "labels.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["file_name", "text", "category", "source_receipt"])
            w.writerows(rows)
        csv_bytes = csv_path.read_bytes()
        zf.writestr(f"{split}/labels.csv", csv_bytes)
        total_bytes += len(csv_bytes)
        hasher.update(csv_bytes)

    print(
        f"[{split}] 写入 {len(rows)} 张真实 OCR 文本行图片（来自 {len(receipt_pairs)} 张扫描票据，"
        f"{total_bytes / (1024**2):.2f} MB），已预打包 {zip_path.name}"
    )
    return {
        "name": split,
        "columns": ["file_name", "text", "category", "source_receipt"],
        "files": len(rows),
        "rows": len(rows),
        "sizeBytes": total_bytes,
        "contentHash": "sha256:" + hasher.hexdigest(),
        "classCounts": class_counts,
        "receipts": len(receipt_pairs),
    }


def main() -> None:
    if (DATA_DIR / "meta.json").exists() and (DATA_DIR / "test" / "labels.csv").exists():
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        tot = meta["train"]["files"] + meta["test"]["files"]
        if tot >= 10000:
            print(f"OCR 数据集已就绪（共 {tot} 张真实图片）：{DATA_DIR}")
            return

    with tempfile.TemporaryDirectory() as td_str:
        td = Path(td_str)
        archive = td / "sroie_master.zip"
        download_repo_zip(archive)

        extract_dir = td / "src"
        print("正在解压原始票据与标注文件…")
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(extract_dir)

        data_root = next(extract_dir.glob("*/data"), None)
        if not data_root:
            raise RuntimeError("未在压缩包中找到 data/ 目录")

        img_dir = data_root / "img"
        box_dir = data_root / "box"
        pairs: list[tuple[str, Path, Path]] = []
        for box_file in sorted(box_dir.glob("*.csv")):
            rid = box_file.stem
            img_file = img_dir / f"{rid}.jpg"
            if img_file.exists():
                pairs.append((rid, img_file, box_file))

        print(f"匹配到 {len(pairs)} 张完整扫描票据，开始按 80%/20% 票据维度切分并裁剪文本行…")
        rng = random.Random(20261122)
        rng.shuffle(pairs)
        n_test = max(1, len(pairs) // 5)
        test_pairs = pairs[:n_test]
        train_pairs = pairs[n_test:]

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        seen_hashes: set[str] = set()
        train_meta = build_split("train", train_pairs, seen_hashes)
        test_meta = build_split("test", test_pairs, seen_hashes)

        total_imgs = train_meta["files"] + test_meta["files"]
        meta = {
            "source": "ICDAR-2019 SROIE (Scanned Receipts OCR and Information Extraction)",
            "totalImages": total_imgs,
            "train": train_meta,
            "test": test_meta,
        }
        (DATA_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OCR 数据集构建完成！总计 {total_imgs:,} 张真实 OCR 文本行图片 + Ground Truth。")


if __name__ == "__main__":
    main()
