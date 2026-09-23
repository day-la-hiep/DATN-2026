#!/usr/bin/env python3
"""Chạy pipeline data-ingest: với mỗi nguồn, chạy lần lượt `<nguồn>/scripts/NN_*.py`
(input -> output); thư mục `*normalize*` chạy cuối cùng để chuẩn hoá + gom output của mọi nguồn.
Gọi bằng tên thư mục hoặc bỏ tiền tố số/dấu chấm (`01_normalize` == `normalize`).

  python run.py --list                  # liệt kê nguồn + script
  python run.py dermo primekg normalize # chạy các nguồn chỉ định, theo thứ tự cho sẵn
  python run.py normalize               # chỉ chuẩn hoá lại từ output có sẵn (nhanh)
  python run.py all                     # mọi nguồn có script, rồi normalize

Chỉ script đánh số `NN_*.py` được chạy tự động. Script nạp DB (`load_*.py` trong normalize:
Qdrant, Neo4j) phải chạy tay — xem README.

Lưu ý `all` gồm cả `dermnet` (bước 03 cào web, chạy lâu) — thường không cần chạy lại.
byt / who / medlineplus không có script: output là dữ liệu đã biên soạn tay từ tài liệu gốc.
"""
import re
import subprocess
import sys
import time
from pathlib import Path

INGEST_DIR = Path(__file__).resolve().parent


def _discover() -> tuple[list[str], str]:
    """Nguồn = thư mục con có scripts/ hoặc output/; thư mục có tên chứa "normalize" chạy cuối."""
    dirs = sorted(
        p.name
        for p in INGEST_DIR.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_")) and ((p / "scripts").is_dir() or (p / "output").is_dir())
    )
    final = next(d for d in dirs if "normalize" in d)
    return [d for d in dirs if d != final], final


SOURCES, FINAL = _discover()


def resolve(name: str) -> str:
    """"normalize" -> "01_normalize" (bỏ tiền tố số/dấu chấm khi so khớp)."""
    for d in SOURCES + [FINAL]:
        if name in (d, re.sub(r"^[\d._-]+", "", d)):
            return d
    return name


def scripts_of(name: str) -> list[Path]:
    return sorted((INGEST_DIR / name / "scripts").glob("[0-9][0-9]_*.py"))


def run_source(name: str) -> bool:
    scripts = scripts_of(name)
    if not scripts:
        print(f"[{name}] không có script (dữ liệu đã biên soạn sẵn trong {name}/output) — bỏ qua")
        return True
    for script in scripts:
        print(f"\n[{name}] >>> {script.name}", flush=True)
        start = time.time()
        if subprocess.run([sys.executable, str(script)], cwd=INGEST_DIR).returncode != 0:
            print(f"[{name}] LỖI ở {script.name} — dừng.")
            return False
        print(f"[{name}] xong {script.name} ({time.time() - start:.1f}s)")
    return True


def main(argv: list[str]) -> int:
    known = SOURCES + [FINAL]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--list":
        for name in known:
            print(f"{name:12s} {', '.join(s.name for s in scripts_of(name)) or '(chỉ có output)'}")
        return 0
    names = SOURCES + [FINAL] if argv == ["all"] else [resolve(a) for a in argv]
    unknown = [n for n in names if n not in known]
    if unknown:
        print(f"Nguồn không hợp lệ: {unknown}. Hợp lệ: {known}")
        return 2
    return 0 if all(run_source(n) for n in names) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
