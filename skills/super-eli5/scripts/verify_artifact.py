#!/usr/bin/env python3
"""驗證 super-eli5 HTML artifact 的完整性與安全邊界。

檢查項目：
1. 只有一個 style 區塊，且其 SHA-256 同時符合 meta 記錄、CSP 的 style-src hash 與 renderer 內建樣式。
2. 內嵌的 canonical spec 與 verification manifest 可以還原、通過驗證，且 SHA-256 符合 meta 記錄。
3. 不含 script、iframe、object、embed、form、link、base、img/video/audio、inline style 屬性、
   on* 事件屬性、javascript: URL、meta refresh；style 內不含 @import 或外部 url()。
4. 所有 href 只能是頁內錨點，或是內嵌 spec evidence 內宣告過的 http(s) locator。
5. 無條件用內嵌 spec 重新 render，結果必須與 artifact bytes 完全相同。
6. 提供 --spec 時再做外部配對驗證：外部 spec 的 canonical hash 必須等於內嵌 hash。

用法：
  python scripts/verify_artifact.py out.html
  python scripts/verify_artifact.py out.html --spec spec.json --json

本工具只讀取檔案，不寫檔、不連網。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_html import CSP, META_RENDERER, META_SPEC_HASH, META_STYLE_HASH, META_VERIFICATION_HASH, RENDERER_VERSION, SPEC_PRE_ID, STYLE_SHA256_HEX, VERIFICATION_PRE_ID, render  # noqa: E402
from validate_spec import VERIFICATION_LEVELS, canonical_json, classify_locator, configure_stdout, load_spec, strict_json_loads, validate_spec  # noqa: E402

VERIFIER_VERSION = "1.4.0"

STYLE_BLOCK = re.compile(r"<style>(.*?)</style>", re.DOTALL)
META_PATTERN = re.compile(r'<meta\s+name="([^"]+)"\s+content="([^"]*)"', re.IGNORECASE)
CSP_PATTERN = re.compile(r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]*)"', re.IGNORECASE)
SPEC_PRE = re.compile(rf'<pre hidden id="{re.escape(SPEC_PRE_ID)}">(.*?)</pre>', re.DOTALL)
VERIFICATION_PRE = re.compile(rf'<pre hidden id="{re.escape(VERIFICATION_PRE_ID)}">(.*?)</pre>', re.DOTALL)
HREF_PATTERN = re.compile(r'href="([^"]*)"', re.IGNORECASE)
FORBIDDEN_MARKUP = {
    "script_tag": re.compile(r"<\s*script\b", re.IGNORECASE),
    "iframe_tag": re.compile(r"<\s*iframe\b", re.IGNORECASE),
    "object_tag": re.compile(r"<\s*(?:object|embed|applet)\b", re.IGNORECASE),
    "form_tag": re.compile(r"<\s*(?:form|input\s+type=\"(?!radio)|button|textarea|select)\b", re.IGNORECASE),
    "link_tag": re.compile(r"<\s*(?:link|base)\b", re.IGNORECASE),
    "media_tag": re.compile(r"<\s*(?:img|video|audio|source|picture)\b", re.IGNORECASE),
    "meta_refresh": re.compile(r'http-equiv="refresh"', re.IGNORECASE),
    "inline_style_attr": re.compile(r"<[^>]*\sstyle\s*=", re.IGNORECASE),
    "event_handler_attr": re.compile(r"<[^>]*\son[a-z]+\s*=", re.IGNORECASE),
    "javascript_url": re.compile(r"<[^>]*=\s*\"[^\"]*javascript\s*:", re.IGNORECASE),
    "src_attr": re.compile(r"<[^>]*\ssrc\s*=", re.IGNORECASE),
    "import_or_external_url_in_css": re.compile(r"@import|url\((?!#)", re.IGNORECASE),
}


def _finding(code: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "message": message}


def verify_html(html_text: str, spec: Any | None = None) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    metas = dict(META_PATTERN.findall(html_text))
    reproduction: dict[str, Any] = {"byte_identical": False}

    styles = STYLE_BLOCK.findall(html_text)
    if len(styles) != 1:
        findings.append(_finding("style_block_count", f"必須剛好有一個 style 區塊，實際 {len(styles)} 個"))
    else:
        style_hex = hashlib.sha256(styles[0].encode("utf-8")).hexdigest()
        style_b64 = base64.b64encode(hashlib.sha256(styles[0].encode("utf-8")).digest()).decode("ascii")
        if metas.get(META_STYLE_HASH) != style_hex:
            findings.append(_finding("style_hash_mismatch", "style 區塊的 SHA-256 與 meta 記錄不符"))
        if style_hex != STYLE_SHA256_HEX:
            findings.append(_finding("style_not_trusted", "style 區塊與 renderer 內建的信任樣式不同；artifact 可能被竄改或由不同版本產生"))
        csp_values = CSP_PATTERN.findall(html_text)
        if len(csp_values) != 1:
            findings.append(_finding("csp_count", f"必須剛好有一個 Content-Security-Policy meta，實際 {len(csp_values)} 個"))
        else:
            csp = csp_values[0]
            if f"'sha256-{style_b64}'" not in csp:
                findings.append(_finding("csp_style_hash_mismatch", "CSP 的 style-src hash 與 style 區塊不符"))
            if csp != CSP:
                findings.append(_finding("csp_unexpected", "CSP 與 renderer 定義不符"))

    if metas.get(META_RENDERER) != RENDERER_VERSION:
        findings.append(_finding("renderer_version_mismatch", f"artifact renderer 版本 {metas.get(META_RENDERER)!r} 與本工具 {RENDERER_VERSION} 不符"))

    for code, pattern in FORBIDDEN_MARKUP.items():
        haystack = styles[0] if code == "import_or_external_url_in_css" and len(styles) == 1 else html_text
        if pattern.search(haystack):
            findings.append(_finding(code, f"artifact 含有被禁止的內容：{code}"))

    embedded_spec: Any | None = None
    verification_levels: dict[str, str] | None = None
    pre_blocks = SPEC_PRE.findall(html_text)
    if len(pre_blocks) != 1:
        findings.append(_finding("embedded_spec_count", f"必須剛好有一個內嵌 spec 區塊，實際 {len(pre_blocks)} 個"))
    else:
        try:
            embedded_spec = strict_json_loads(html.unescape(pre_blocks[0]))
        except ValueError as exc:
            findings.append(_finding("embedded_spec_invalid_json", f"內嵌 spec 不是合法 JSON：{exc}"))
        if embedded_spec is not None:
            embedded_hash = hashlib.sha256(canonical_json(embedded_spec).encode("utf-8")).hexdigest()
            if metas.get(META_SPEC_HASH) != embedded_hash:
                findings.append(_finding("embedded_spec_hash_mismatch", "內嵌 spec 的 SHA-256 與 meta 記錄不符；artifact 或 spec 已被竄改"))
            validation = validate_spec(embedded_spec)
            for item in validation.errors:
                findings.append(_finding("embedded_spec_invalid", f"{item.code}: {item.message}"))

    verification_blocks = VERIFICATION_PRE.findall(html_text)
    if len(verification_blocks) != 1:
        findings.append(_finding("verification_manifest_count", f"必須剛好有一個 verification manifest，實際 {len(verification_blocks)} 個"))
    else:
        try:
            manifest = strict_json_loads(html.unescape(verification_blocks[0]))
            levels = manifest.get("levels") if isinstance(manifest, dict) and manifest.get("version") == 1 else None
            if not isinstance(levels, dict) or not all(isinstance(key, str) and value in VERIFICATION_LEVELS for key, value in levels.items()):
                raise ValueError("manifest 必須是 version=1 且 levels 為合法 evidence→level 對照")
            verification_levels = levels
            manifest_hash = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
            reproduction["verification_sha256"] = manifest_hash
            if metas.get(META_VERIFICATION_HASH) != manifest_hash:
                findings.append(_finding("verification_manifest_hash_mismatch", "verification manifest 的 SHA-256 與 meta 記錄不符"))
            if isinstance(embedded_spec, dict):
                expected_ids = {item["id"] for item in embedded_spec.get("evidence", []) if isinstance(item, dict) and item.get("status") == "verified" and isinstance(item.get("id"), str)}
                if set(levels) != expected_ids:
                    findings.append(_finding("verification_manifest_evidence_mismatch", "verification manifest 必須剛好覆蓋全部 verified evidence"))
        except ValueError as exc:
            findings.append(_finding("verification_manifest_invalid", f"verification manifest 不合法：{exc}"))

    if isinstance(embedded_spec, dict) and verification_levels is not None and not any(item["code"] == "embedded_spec_invalid" for item in findings):
        try:
            rerendered = render(embedded_spec, verification_levels=verification_levels)
            reproduction["byte_identical"] = rerendered == html_text
            if not reproduction["byte_identical"]:
                findings.append(
                    _finding(
                        "embedded_render_mismatch",
                        "用內嵌 spec 與檢驗 manifest 重新 render 的結果與 artifact bytes 不同；可見正文或其他 renderer 輸出已被修改",
                    )
                )
        except ValueError as exc:
            findings.append(_finding("verification_manifest_invalid", str(exc)))

    allowed_links: set[str] = set()
    if isinstance(embedded_spec, dict):
        for item in embedded_spec.get("evidence", []) or []:
            locator = item.get("locator") if isinstance(item, dict) else None
            if isinstance(locator, str) and classify_locator(locator) == "url":
                allowed_links.add(html.escape(locator, quote=True))
    for href in HREF_PATTERN.findall(html_text):
        if href.startswith("#"):
            continue
        if href in allowed_links:
            continue
        findings.append(_finding("link_not_allowed", f"href 不是頁內錨點，也不是 evidence 宣告過的 URL：{href[:80]}"))

    pair: dict[str, Any] = {}
    if spec is not None:
        try:
            spec_hash = hashlib.sha256(canonical_json(spec).encode("utf-8")).hexdigest()
        except (TypeError, ValueError, RecursionError) as exc:
            findings.append(_finding("pair_spec_invalid_json", f"提供的 spec 無法轉成 canonical JSON：{exc}"))
        else:
            pair["spec_sha256"] = spec_hash
            if metas.get(META_SPEC_HASH) != spec_hash:
                findings.append(_finding("pair_spec_hash_mismatch", "提供的 spec 與 artifact 內嵌 hash 不符"))
            else:
                validation = validate_spec(spec)
                if validation.ok:
                    pair["byte_identical"] = reproduction["byte_identical"]
                else:
                    findings.append(_finding("pair_spec_invalid", "提供的 spec 未通過驗證，無法重新 render"))

    return {
        "verifier_version": VERIFIER_VERSION,
        "status": "PASS" if not findings else "FAIL",
        "renderer_version": metas.get(META_RENDERER),
        "spec_sha256": metas.get(META_SPEC_HASH),
        "style_sha256": metas.get(META_STYLE_HASH),
        "html_sha256": hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
        "reproduction": reproduction,
        "pair": pair,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="驗證 super-eli5 HTML artifact")
    parser.add_argument("html", help="HTML 路徑")
    parser.add_argument("--spec", type=Path, default=None, help="對應的 spec；提供後做配對與 byte 重現驗證")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出結果")
    args = parser.parse_args(argv)
    configure_stdout()

    try:
        html_text = Path(args.html).read_bytes().decode("utf-8")
        spec = load_spec(args.spec) if args.spec else None
    except (OSError, ValueError) as exc:
        report = {"verifier_version": VERIFIER_VERSION, "status": "FAIL", "findings": [_finding("input_unreadable", str(exc))]}
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"FAIL input_unreadable: {exc}")
        return 1
    report = verify_html(html_text, spec)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['status']}  html_sha256={report['html_sha256']}  spec_sha256={report['spec_sha256']}  pair={report['pair']}")
        for item in report["findings"]:
            print(f"  ERROR {item['code']}: {item['message']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
