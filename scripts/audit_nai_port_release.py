"""Audit a local NAI-port source candidate and its recorded verification artifacts.

Does not call NovelAI, install detector runtimes, or publish a release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from source_archive import (
    PROJECT_ROOT, _working_tree_entries, _write_archive, project_version,
    verify_source_archive,
)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve()
    evidence_root = args.evidence_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    reports = {}
    for relative in (
        "final-package/browser/report.json", "focused/browser/report.json",
        "sam3/browser/report.json", "hands/browser/report.json",
        "queue-seed-fix/browser/report.json", "provider-regression/report.json",
        "inpaint-regression/report.json", "metadata-regression/report.json",
        "native/report.json", "sam3/native/report.json", "hands/native/report.json",
    ):
        path = evidence_root / relative
        data = json.loads(path.read_text())
        assert data["status"] == "passed", relative
        assert not data.get("page_errors"), relative
        for key in ("live_nai_requests", "live_requests"):
            if key in data:
                assert data[key] == 0, (relative, key)
        if "generation_posts" in data:
            assert data["generation_posts"] == [], (relative, "generation_posts")
        reports[relative] = {"sha256": digest(path), "data": data}

    xml = evidence_root / "final-package/full-regression.xml"
    suites = ET.parse(xml).getroot().findall("testsuite")
    assert suites and all(int(s.attrib["failures"]) == int(s.attrib["errors"]) == 0 for s in suites)
    test_summary = {key: sum(int(s.attrib[key]) for s in suites)
                    for key in ("tests", "failures", "errors", "skipped")}
    test_summary["passed"] = test_summary["tests"] - test_summary["skipped"]

    preserved = {}
    metadata = reports["metadata-regression/report.json"]["data"]
    preserved[metadata["real_existing_image"]] = metadata["image_sha256"]
    sam3 = reports["sam3/native/report.json"]["data"]
    preserved[sam3["source_path"]] = sam3["sha256"]["source"]
    preserved[sam3["model_path"]] = sam3["sha256"]["model"]
    preserved.update(reports["hands/native/report.json"]["data"]["sha256"])
    assert all(digest(path) == expected for path, expected in preserved.items())

    verify_source_archive(archive)
    entries = _working_tree_entries()
    prefix = f"anima-app-{project_version()}"
    with zipfile.ZipFile(archive) as source:
        assert set(source.namelist()) == {f"{prefix}/{name}" for name in entries}
        for name, content in entries.items():
            assert source.read(f"{prefix}/{name}") == content, name
    assert archive.with_name(archive.name + ".sha256").read_text().split()[0] == digest(archive)
    with tempfile.TemporaryDirectory(prefix="anima-repro-audit-") as temporary:
        repeated = Path(temporary) / archive.name
        _write_archive(repeated, prefix, entries)
        assert digest(repeated) == digest(archive), "archive is not reproducible"

    environment = os.environ.copy()
    environment.pop("NAI_ACCESS_TOKEN", None)
    environment.pop("NAI_API_TOKEN", None)
    package = subprocess.run(
        [sys.executable, "scripts/package_dry_run.py"], cwd=PROJECT_ROOT,
        env=environment, text=True, capture_output=True,
    )
    (output / "package-dry-run.log").write_text(package.stdout + package.stderr)
    assert package.returncode == 0, "package dry-run failed; inspect package-dry-run.log"
    assert "package dry-run passed:" in package.stdout

    report = {
        "status": "passed", "version": project_version(),
        "evidence": "source content equality, repeat archive, preserved originals/weights, recorded local/mock acceptance, isolated wheel install and dry-run",
        "archive": {"path": str(archive), "sha256": digest(archive),
                    "bytes": archive.stat().st_size, "files": len(entries),
                    "content_matches_worktree": True, "reproducible": True},
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip(),
        "git_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=PROJECT_ROOT, text=True).strip(),
        "regression": {**test_summary, "xml_sha256": digest(xml)},
        "package_dry_run": {"status": "passed", "log_sha256": digest(output / "package-dry-run.log")},
        "reports": reports, "preserved_files": preserved,
        "source_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(entries.items())},
        "live_nai_requests_this_audit": 0,
        "limits": ["dirty worktree source candidate, no commit/tag/publish/deploy",
                   "prior native reports use separate CPU environments and limited image fixtures",
                   "optional detector runtimes/models not bundled or installed in app environment",
                   "live new-port endpoint acceptance, correction quality and Anlas billing unverified",
                   "Windows GUI and GPU inference unverified"],
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "archive", "regression", "package_dry_run")}, indent=2))


if __name__ == "__main__":
    main()
