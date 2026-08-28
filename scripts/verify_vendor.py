from __future__ import annotations

import argparse
import base64
import csv
import hashlib
from io import StringIO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "vendor" / "python_packages"
DISTRIBUTIONS = (
    ("comfy_aimdo", "comfy_aimdo-0.3.0.dist-info"),
    ("comfy_kitchen", "comfy_kitchen-0.2.8.dist-info"),
)
TEXT_SUFFIXES = {".md", ".py", ".txt", ".toml", ".yaml", ".yml"}
IGNORED_LOCAL_SUFFIXES = {".pyc", ".pyd"}


def _distribution_files(package: str, metadata: str) -> list[Path]:
    files: list[Path] = []
    for root in (PACKAGE_ROOT / package, PACKAGE_ROOT / metadata):
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix.lower() not in IGNORED_LOCAL_SUFFIXES
        )
    return sorted(files)


def _record_hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}"


def _distribution_rows(package: str, metadata: str) -> list[tuple[str, str, str]]:
    record_name = f"{metadata}/RECORD"
    rows: list[tuple[str, str, str]] = []
    for path in _distribution_files(package, metadata):
        relative_name = path.relative_to(PACKAGE_ROOT).as_posix()
        if relative_name == record_name:
            continue
        data = path.read_bytes()
        rows.append((relative_name, _record_hash(data), str(len(data))))
    rows.append((record_name, "", ""))
    return sorted(rows)


def update_records() -> None:
    for package, metadata in DISTRIBUTIONS:
        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerows(_distribution_rows(package, metadata))
        (PACKAGE_ROOT / metadata / "RECORD").write_text(buffer.getvalue(), encoding="utf-8", newline="")


def verify_records() -> list[str]:
    errors: list[str] = []
    for package, metadata in DISTRIBUTIONS:
        record_path = PACKAGE_ROOT / metadata / "RECORD"
        expected = _distribution_rows(package, metadata)
        with record_path.open("r", encoding="utf-8", newline="") as handle:
            actual = [tuple(row) for row in csv.reader(handle)]
        if actual != expected:
            errors.append(f"{record_path.relative_to(PROJECT_ROOT)} is stale; run scripts/verify_vendor.py --update")
    return errors


def verify_product_boundary() -> list[str]:
    errors: list[str] = []
    for path in (PROJECT_ROOT / "vendor").rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="strict")
        if "gemmanima" in text.casefold():
            errors.append(f"cross-product marker remains in {path.relative_to(PROJECT_ROOT)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify disclosed vendored package integrity")
    parser.add_argument("--update", action="store_true", help="regenerate RECORD files from tracked vendor files")
    arguments = parser.parse_args(argv)
    if arguments.update:
        update_records()
    errors = [*verify_records(), *verify_product_boundary()]
    if errors:
        raise SystemExit("\n".join(errors))
    print("vendor verification passed: RECORD hashes and Anima APP product boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
