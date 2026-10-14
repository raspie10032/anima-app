"""Verify a pinned 2.4.6 working-tree candidate against regression and artifact evidence.

This audit never connects to NovelAI, installs models, or restarts services.
It rejects missing/failed evidence rather than treating a checklist as proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import zipfile

import source_archive


ROOT = Path(__file__).resolve().parents[1]
PIN = "4de914676de8ca313b8389f4303754045a6a9cfb"
OBSERVED_UPSTREAM = "ed96a4c4394a8af8f1644218a4feae73f2dc62c9"
SOURCE_FILES = (
    "nai_api.py", "generators.py", "detailer.py", "detailer_matching.py",
    "converters.py", "diagnostics.py", "image_utils.py", "references.py",
    "wd_tagger.py", "tagger_progress.py", "web/characters.js",
    "locales/ko/nodeDefs.json", "locales/ja/nodeDefs.json",
    "errors.py", "web/errors.js", "web/error_messages.json", "runtime_control.py",
)
REQUIREMENTS = {
    "medium": ("test_novelai_medium", "test_medium_effective_wire_settings_and_original_preservation", 7),
    "audit": ("test_novelai_audit", "test_failed_tight_retry_retains_latest_scores_and_exact_skip_reason", 6),
    "tagger": ("test_novelai_tagger", "test_real_queue_preview_preserves_selected_model_manifest_png", 9),
    "characters": ("test_novelai_character_slots", "test_each_model_exact_limit_and_overflow", 8),
    "language": ("test_novelai_language", "test_blocked_storage_and_cross_tab_clear_follow_browser_default", 10),
    "errors": ("test_novelai_errors", "test_partial_error_round_trips_manifest_and_png", 12),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(args, cwd=ROOT, env=None):
    return subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


def browser_evidence(path, minimum=1):
    report = read_json(path)
    check(report.get("status", "passed") == "passed", f"browser failed: {path}")
    check(report.get("page_errors") == [], f"browser errors or missing page-error evidence: {path}")
    for key in ("blocked_requests", "external_http_attempts"):
        check(not report.get(key), f"attempted external request: {path}")
    live_keys = ("live_nai_calls", "live_nai_requests", "live_requests")
    check(any(report.get(key) == 0 for key in live_keys), f"missing no-live-request evidence: {path}")
    cases = report.get("cases", report.get("checks", report.get("checked", [])))
    check(len(cases) >= minimum, f"missing browser scenarios: {path}")
    for case in cases:
        if isinstance(case, dict):
            if "status" in case:
                check(case["status"] == "passed", f"failed browser case: {case}")
            else:
                check(case.get("terminal_state_confirmed") and case.get("completed_manifests_checked", 0) > 0
                      and set(case.get("statuses", [])) <= {"completed", "cancelled"}, f"incomplete queue case: {case}")
    if report.get("address"):
        address = urlparse(report["address"])
        check(address.hostname == "127.0.0.1", "browser test must bind loopback")
        with socket.socket() as sock:
            sock.settimeout(.5)
            check(sock.connect_ex((address.hostname, address.port)) != 0, "test listener still active")
    return {"sha256": digest(path.read_bytes()), "cases": cases, "page_errors": [], "live_nai_requests": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--wheel-report", type=Path, required=True)
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--installed-source", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    xml = evidence / "full-regression.xml"
    cases = list(ET.parse(xml).iter("testcase"))
    failures = [case.attrib for case in cases if case.find("failure") is not None or case.find("error") is not None]
    skipped = [case.attrib for case in cases if case.find("skipped") is not None]
    passed = [case for case in cases if case.find("skipped") is None]
    check(cases and not failures, "regression evidence missing or failed")
    check(len(passed) >= 1054, "full combined regression evidence is incomplete")
    check(len(skipped) == 1 and "launchers" in skipped[0]["classname"], "unexpected regression skips")
    requirements = {}
    for feature, (module, required, minimum) in REQUIREMENTS.items():
        tests = [case.attrib["name"] for case in passed if module in case.attrib.get("classname", "")]
        check(any(name.startswith(required) for name in tests), f"required regression missing: {feature}")
        requirements[feature] = {"tests": tests, "browser": browser_evidence(evidence / "browser" / feature / "report.json", minimum)}
    baseline = {}
    for feature, minimum in {"remaining": 9, "focused": 7, "provider": 18, "inpaint": 8,
                             "hands": 8, "queue_seed": 6}.items():
        baseline[feature] = browser_evidence(evidence / "browser" / feature / "report.json", minimum)
    native = read_json(evidence / "native/report.json")
    check(native.get("status") == "passed" and len(native["models"]) == 3, "native CPU tagger evidence incomplete")
    check(native["nai_requests"] == 0 and native["external_http_attempts"] == [], "native run was not offline")
    for model in native["models"]:
        check(model["status"] == "passed" and [r["character"] for r in model["regions"]] == [2, 1], "native matching failure")
    originals = {}
    for name in SOURCE_FILES:
        blob = subprocess.run(["git", "show", f"{PIN}:{name}"], cwd=args.source_repo, check=True, capture_output=True).stdout
        installed = (args.installed_source / name).read_bytes()
        newer = subprocess.run(["git", "show", f"{OBSERVED_UPSTREAM}:{name}"], cwd=args.source_repo, check=True, capture_output=True).stdout
        check(installed in (blob, newer), f"unexplained installed source change: {name}")
        originals[name] = {"pinned_sha256": digest(blob), "installed_sha256": digest(installed),
                           "equal": blob == installed, "matches_observed_upstream": installed == newer}

    wheel_report = read_json(args.wheel_report)
    check(wheel_report["status"] == "passed" and wheel_report["isolated_install_import_cli"], "wheel smoke missing")
    wheel_path = args.wheel_report.parent / wheel_report["wheel"]
    check(digest(wheel_path.read_bytes()) == wheel_report["sha256"], "wheel changed after smoke")
    with zipfile.ZipFile(wheel_path) as wheel:
        for path in (ROOT / "src/anima_app").rglob("*"):
            if path.is_file() and path.suffix in {".py", ".js", ".json"}:
                name = path.relative_to(ROOT / "src").as_posix()
                check(wheel.read(name) == path.read_bytes(), f"wheel no longer matches: {name}")
    source_archive.verify_source_archive(args.archive)
    entries = source_archive._working_tree_entries()
    prefix = f"anima-app-{source_archive.project_version()}"
    source_hashes = {name: digest(content) for name, content in sorted(entries.items())}
    with zipfile.ZipFile(args.archive) as archive:
        check(set(archive.namelist()) == {f"{prefix}/{name}" for name in source_hashes}, "source ZIP inventory differs")
        for name, content in entries.items():
            check(archive.read(f"{prefix}/{name}") == content, f"source ZIP differs: {name}")
        with tempfile.TemporaryDirectory(prefix="anima-final-extract-") as temp:
            archive.extractall(temp)
            checkout = Path(temp) / prefix
            environment = os.environ.copy()
            environment.pop("NAI_ACCESS_TOKEN", None)
            environment.pop("NAI_API_TOKEN", None)
            environment.update(PYTHONPATH=str(checkout / "src"))
            vendor = command([sys.executable, "scripts/verify_vendor.py"], checkout, environment)
            command([sys.executable, "-m", "anima_app.cli", "--help"], checkout, environment)
            command([sys.executable, "-c", "from anima_app.providers.novelai import NovelAIRequest, generate; from anima_app.config import AppPaths; from pathlib import Path; import tempfile; t=tempfile.TemporaryDirectory(); r=generate(NovelAIRequest(prompt='package smoke',model='nai-diffusion-5-full-medium'), paths=AppPaths(Path(t.name)), dry_run=True); assert r.manifest_path.is_file(); t.cleanup()"], checkout, environment)
    with tempfile.TemporaryDirectory(prefix="anima-reproducibility-") as temp:
        repeated, _ = source_archive.build_source_archive(Path(temp))
        check(repeated.read_bytes() == args.archive.read_bytes(), "source ZIP not reproducible")
    report = {
        "status": "passed", "source_pin": PIN, "observed_upstream": OBSERVED_UPSTREAM,
        "scope": "2.4.6 local/mock candidate acceptance; no live NAI or public release",
        "git_head": command(["git", "rev-parse", "HEAD"]), "git_branch": command(["git", "branch", "--show-current"]),
        "git_status": command(["git", "status", "--short"]),
        "regression": {"passed": len(passed), "skipped": skipped, "xml_sha256": digest(xml.read_bytes())},
        "requirements": requirements, "baseline_browser": baseline, "native_sha256": digest((evidence / "native/report.json").read_bytes()),
        "originals": originals, "wheel": wheel_report, "source_archive": {"name": args.archive.name,
            "sha256": digest(args.archive.read_bytes()), "bytes": args.archive.stat().st_size, "file_count": len(entries),
            "reproducible": True, "extract_vendor_cli_dry_run": True, "vendor_check": vendor},
        "source_sha256": source_hashes, "live_nai_requests": 0,
        "limitations": ["No live NAI account, image or reference encoding calls; API acceptance, quality and billing unverified",
            "Native inference uses existing ComfyUI CPU dependencies and cached weights, supplied face boxes only",
            "App optional dependency installation, actual new downloads, GPU and Windows execution unverified",
            "2.5.0 reference inset and portable character assets are after the fixed 2.4.6 scope",
            "Dirty source candidate; not committed, pushed, tagged or deployed"],
    }
    (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(evidence / "report.json"), "tests": len(passed), "source_files": len(entries), "source_sha256": report["source_archive"]["sha256"]}))


if __name__ == "__main__":
    main()
