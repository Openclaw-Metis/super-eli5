#!/usr/bin/env python3
"""Repository-local release contract for GitHub Actions.

This intentionally uses only the standard library so the same checks run on
Ubuntu and Windows without installing the external authoring toolkit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / "skills" / "super-eli5"
REQUIRED_BLOCKS = ("role", "decision_boundary", "workflow", "output_contract", "default_follow_through_policy", "examples")
REQUIRED_MIGRATION_HEADINGS = ("Rename", "Deprecate", "Merge", "Split", "Compatibility", "Migration Evidence")
REQUIRED_TAGS = {"should-trigger", "should-not-trigger", "near-miss", "overlap-neighbor", "happy-path", "edge-case", "failure-mode"}
REQUIRED_LANGUAGES = {"zh", "en", "mixed"}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def finding(code: str, message: str, path: Path | None = None) -> dict[str, str]:
    item = {"code": code, "message": message}
    if path is not None:
        item["path"] = str(path.relative_to(REPO_ROOT))
    return item


def load_json(path: Path, findings: list[dict[str, str]]) -> Any | None:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    except (OSError, ValueError) as exc:
        findings.append(finding("json_invalid", str(exc), path))
        return None


def audit() -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    attributes = REPO_ROOT / ".gitattributes"
    if attributes.read_text(encoding="utf-8").strip() != "* text=auto eol=lf":
        findings.append(finding("line_ending_policy_missing", ".gitattributes must force LF for text files", attributes))

    for path in sorted(SKILL_ROOT.rglob("*.json")):
        load_json(path, findings)

    skill_md = SKILL_ROOT / "SKILL.md"
    skill_text = skill_md.read_text(encoding="utf-8")
    version_match = re.search(r"^version:\s*([^\s]+)\s*$", skill_text, flags=re.MULTILINE)
    version = version_match.group(1) if version_match else None
    if version is None:
        findings.append(finding("skill_version_missing", "SKILL.md frontmatter needs a version", skill_md))
    for block in REQUIRED_BLOCKS:
        if not re.search(rf"<{block}>.+?</{block}>", skill_text, flags=re.DOTALL):
            findings.append(finding("skill_block_missing", f"Missing non-empty <{block}> block", skill_md))
    steps = re.findall(r"^Step\s+\d+:.*$", skill_text, flags=re.MULTILINE)
    if len(steps) < 2:
        findings.append(finding("workflow_unparseable", "Workflow needs parseable Step N headings", skill_md))
    for phrase in ("Directly do", "Ask first", "Stop and report"):
        if phrase not in skill_text:
            findings.append(finding("follow_through_missing", f"Missing {phrase} section", skill_md))

    readiness = SKILL_ROOT / "references" / "readiness_report.md"
    readiness_text = readiness.read_text(encoding="utf-8")
    if version and version not in readiness_text:
        findings.append(finding("readiness_version_stale", f"Readiness report does not mention {version}", readiness))
    if not re.search(r"Audit date:\s*\d{4}-\d{2}-\d{2}", readiness_text):
        findings.append(finding("readiness_date_missing", "Readiness report needs Audit date: YYYY-MM-DD", readiness))

    migration = SKILL_ROOT / "references" / "migration-governance.md"
    migration_text = migration.read_text(encoding="utf-8") if migration.exists() else ""
    for heading in REQUIRED_MIGRATION_HEADINGS:
        if not re.search(rf"^#+\s+.*{re.escape(heading)}", migration_text, flags=re.IGNORECASE | re.MULTILINE):
            findings.append(finding("migration_heading_missing", f"Missing migration heading: {heading}", migration))

    eval_path = SKILL_ROOT / "assets" / "evals" / "evals.json"
    eval_payload = load_json(eval_path, findings)
    if isinstance(eval_payload, dict) and isinstance(eval_payload.get("evals"), list):
        cases = eval_payload["evals"]
        tags = {tag for case in cases for tag in case.get("coverage_tags", [])}
        languages = {case.get("language") for case in cases}
        if not REQUIRED_TAGS <= tags:
            findings.append(finding("eval_tags_missing", f"Missing eval tags: {sorted(REQUIRED_TAGS - tags)}", eval_path))
        if not REQUIRED_LANGUAGES <= languages:
            findings.append(finding("eval_languages_missing", f"Missing eval languages: {sorted(REQUIRED_LANGUAGES - languages)}", eval_path))
        for index, case in enumerate(cases):
            for expectation in case.get("expectations", []):
                if not isinstance(expectation, str) or len(expectation.strip()) < 10:
                    findings.append(finding("eval_expectation_too_weak", f"evals[{index}] has an unverifiable expectation", eval_path))
    else:
        findings.append(finding("eval_shape_invalid", "evals.json must contain an evals array", eval_path))

    for markdown in sorted(SKILL_ROOT.rglob("*.md")):
        text = markdown.read_text(encoding="utf-8")
        for href in MARKDOWN_LINK.findall(text):
            target = href.split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (markdown.parent / target).resolve()
            if not resolved.is_relative_to(SKILL_ROOT.resolve()) or not resolved.exists():
                findings.append(finding("reference_missing", f"Broken local reference: {href}", markdown))

    workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if "tests/release_contract.py" not in workflow.read_text(encoding="utf-8"):
        findings.append(finding("ci_release_gate_missing", "CI must execute the repository-local release contract", workflow))

    return {
        "status": "PASS" if not findings else "FAIL",
        "skill_version": version,
        "checks": {
            "json_files": len(list(SKILL_ROOT.rglob("*.json"))),
            "workflow_steps": len(steps),
            "markdown_files": len(list(SKILL_ROOT.rglob("*.md"))),
        },
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the super-eli5 repository release contract")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"release_contract: {report['status']}")
        for item in report["findings"]:
            print(f"  {item['code']}: {item['message']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
