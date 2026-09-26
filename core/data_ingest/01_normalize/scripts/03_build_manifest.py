#!/usr/bin/env python3
"""Ghi `01_normalize/output/manifest.json`: liệt kê mọi file đã chuẩn hoá (kích thước, sha256,
số bản ghi) để biết bộ data đang deploy được build từ đâu và phát hiện file bị đổi tay.

Chạy: python data-ingest/01_normalize/scripts/03_build_manifest.py
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT_ROOT = Path(__file__).resolve().parents[1] / "output"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def count_records(path: Path) -> int | None:
    if path.suffix == ".csv":
        with path.open(encoding="utf-8") as f:
            return sum(1 for _ in f) - 1
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict) and isinstance(data.get("terms"), list):
            return len(data["terms"])
    return None


def main() -> int:
    files = sorted(p for p in OUT_ROOT.rglob("*") if p.is_file() and p.name != "manifest.json")
    if not files:
        print("[lỗi] 01_normalize/output trống — chạy 01–02 trước")
        return 1
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": {
            str(p.relative_to(OUT_ROOT)): {
                "bytes": p.stat().st_size,
                "records": count_records(p),
                "sha256": sha256(p),
            }
            for p in files
        },
    }
    (OUT_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for name, info in manifest["files"].items():
        print(f"{name:55s} {info['records']!s:>8} bản ghi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
