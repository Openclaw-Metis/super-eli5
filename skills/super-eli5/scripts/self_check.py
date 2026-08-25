#!/usr/bin/env python3
"""super-eli5 自我檢查：對內建範例跑完整的 validate → bind-check → render ×2 → verify 流程。

用途：
- 安裝到新環境後確認 scripts 可用、範例仍然通過、renderer 仍是決定性的。
- 修改 validator / renderer 後的最小回歸測試（repo 內另有完整 unittest）。

用法：
  python scripts/self_check.py
  python scripts/self_check.py --json

只讀取 skill 內的檔案；輸出只寫進暫存目錄，結束後自動刪除，不會覆寫任何既有檔案。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_html import RENDERER_VERSION, render, write_text_atomic  # noqa: E402
from validate_spec import VALIDATOR_VERSION, configure_stdout, load_spec, spec_sha256, validate_spec  # noqa: E402
from verify_artifact import verify_html  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = SKILL_ROOT / "assets" / "examples"
SOURCES_DIR = EXAMPLES_DIR / "sources"


def check_example(path: Path, workdir: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {"example": path.name, "status": "PASS", "problems": []}
    try:
        spec = load_spec(path)
    except (OSError, ValueError) as exc:
        entry["status"] = "FAIL"
        entry["problems"].append(f"spec_unreadable: {exc}")
        return entry
    validation = validate_spec(spec, source_root=SOURCES_DIR, check_quotes=True)
    entry["spec_sha256"] = spec_sha256(spec)
    entry["verification"] = dict(sorted(validation.verification.items()))
    entry["warnings"] = [item.code for item in validation.warnings]
    if not validation.ok:
        entry["status"] = "FAIL"
        entry["problems"].extend(f"{item.code}: {item.message}" for item in validation.errors)
        return entry
    first = render(spec)
    second = render(spec)
    if first != second:
        entry["status"] = "FAIL"
        entry["problems"].append("render_not_deterministic")
    target = workdir / (path.stem + ".html")
    write_text_atomic(target, first, force=False, workspace=workdir)
    on_disk = target.read_text(encoding="utf-8")
    report = verify_html(on_disk, spec)
    entry["html_sha256"] = report["html_sha256"]
    entry["bytes"] = len(on_disk.encode("utf-8"))
    if report["status"] != "PASS":
        entry["status"] = "FAIL"
        entry["problems"].extend(f"{item['code']}: {item['message']}" for item in report["findings"])
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="對內建範例執行 super-eli5 自我檢查")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出結果")
    args = parser.parse_args(argv)
    configure_stdout()

    examples = sorted(EXAMPLES_DIR.glob("*.json"))
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="super-eli5-selfcheck-") as tmp:
        workdir = Path(tmp)
        for path in examples:
            results.append(check_example(path, workdir))
    status = "PASS" if results and all(item["status"] == "PASS" for item in results) else "FAIL"
    report = {
        "status": status,
        "validator_version": VALIDATOR_VERSION,
        "renderer_version": RENDERER_VERSION,
        "example_count": len(results),
        "results": results,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"self_check: {status} ({len(results)} examples; validator {VALIDATOR_VERSION}, renderer {RENDERER_VERSION})")
        for item in results:
            print(f"  {item['status']}  {item['example']}  verification={item.get('verification')}")
            for problem in item["problems"]:
                print(f"      - {problem}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
