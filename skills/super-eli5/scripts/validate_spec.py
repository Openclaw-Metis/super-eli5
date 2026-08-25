#!/usr/bin/env python3
"""super-eli5 story spec v1 驗證器。

只用 Python 標準函式庫，不連網、不執行外部程式、不安裝套件。

驗證三個層次：
1. 結構：欄位、型別、長度上限、ID 唯一性、參照完整性。
2. 語意：五種 story grammar（concept / module / tradeoff / incident / metric）各自的契約。
3. 證據：analogy / inferred / verified 三層真相的 provenance 規則。

`verified` 在這裡有三個檢驗等級，等級只會由實際檢查結果決定，不會憑宣告升級：
- structural：locator、quote 與不可變識別（commit_sha / content_sha256 / retrieved_at）都存在。
- content-bound：本機來源檔案的 SHA-256 與 content_sha256 相符。
- quote-checked：quote 真的出現在來源檔案（若有 line_start / line_end，則限定在該範圍）。

用法：
  python scripts/validate_spec.py spec.json
  python scripts/validate_spec.py spec.json --source-root . --check-quotes
  python scripts/validate_spec.py spec.json --source-root . --check-quotes --bind --out spec.bound.json
  python scripts/validate_spec.py spec.json --json

安全邊界：
- 只讀取 --source-root 之內的檔案；locator 逃出路徑邊界會被拒絕（workspace boundary）。
- --bind 只寫到 --out；目標已存在時不得覆寫，除非明確加 --force（no-clobber）。
- 寫檔採暫存檔＋原子 os.replace；失敗時原檔不變，這就是 rollback 路徑。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SPEC_VERSION = 1
VALIDATOR_VERSION = "1.0.0"

LANGUAGES = ("zh-TW", "zh-CN", "en")
MODES = ("concept", "module", "tradeoff", "incident", "metric")
STATUSES = ("analogy", "inferred", "verified")
VERIFICATION_LEVELS = ("structural", "content-bound", "quote-checked")
INCIDENT_KINDS = ("normal", "first_break", "detection", "mitigation", "recovery")

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,64}$")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
URL_PATTERN = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)
ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:/|\\\\|[A-Za-z]:[\\/]|~)")
LOCAL_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_./ -]*$")

BOUNDS = {
    "scenes": (1, 7),
    "nodes_per_scene": (2, 6),
    "edges_per_scene": (0, 12),
    "trace": (0, 24),
    "glossary": (0, 16),
    "teach_back": (1, 3),
    "evidence": (1, 40),
    "failure_lens": (1, 8),
    "misconceptions": (1, 8),
    "options": (2, 5),
    "timeline": (2, 24),
    "lineage": (1, 12),
}

MAX_LEN = {
    "title": 80,
    "audience": 40,
    "one_liner": 60,
    "analogy.text": 300,
    "analogy.limits": 300,
    "ladder": 400,
    "scene.title": 60,
    "scene.caption": 200,
    "node.label": 30,
    "node.note": 160,
    "edge.label": 30,
    "trace.text": 200,
    "failure.what_breaks": 120,
    "failure.symptom": 200,
    "teach.question": 160,
    "teach.answer": 300,
    "glossary.term": 40,
    "glossary.plain": 160,
    "evidence.claim": 300,
    "evidence.locator": 512,
    "evidence.quote": 240,
    "evidence.reasoning": 300,
    "evidence.note": 200,
    "generic": 400,
}

TOP_LEVEL_REQUIRED = (
    "version",
    "language",
    "mode",
    "title",
    "audience",
    "one_liner",
    "analogy",
    "ladder",
    "scenes",
    "failure_lens",
    "teach_back",
    "evidence",
    "mode_data",
)
TOP_LEVEL_OPTIONAL = ("trace", "glossary")


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    path: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "message": self.message, "path": self.path}


@dataclass
class ValidationResult:
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    verification: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code: str, message: str, path: str = "") -> None:
        self.errors.append(Finding("error", code, message, path))

    def warn(self, code: str, message: str, path: str = "") -> None:
        self.warnings.append(Finding("warning", code, message, path))

    def as_dict(self) -> dict[str, Any]:
        return {
            "validator_version": VALIDATOR_VERSION,
            "status": "PASS" if self.ok else "FAIL",
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "verification": dict(sorted(self.verification.items())),
            "verification_summary": _summarize_levels(self.verification),
            "errors": [item.as_dict() for item in self.errors],
            "warnings": [item.as_dict() for item in self.warnings],
        }


def _summarize_levels(levels: dict[str, str]) -> dict[str, int]:
    summary = {level: 0 for level in VERIFICATION_LEVELS}
    for value in levels.values():
        if value in summary:
            summary[value] += 1
    return summary


# ---------------------------------------------------------------------------
# canonical form
# ---------------------------------------------------------------------------


def canonical_json(spec: Any) -> str:
    """固定鍵序、緊湊分隔、保留 Unicode；同一份 spec 永遠得到同一串字。"""

    return json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def spec_sha256(spec: Any) -> str:
    return hashlib.sha256(canonical_json(spec).encode("utf-8")).hexdigest()


def load_spec(path: Path | str) -> Any:
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# low-level checks
# ---------------------------------------------------------------------------


def _is_text(value: Any) -> bool:
    return isinstance(value, str)


def text_units(value: str) -> int:
    """以「全形字寬」計算長度：CJK / 全形字算 2，英數與半形符號算 1。

    長度上限以全形字數宣告（例如 one_liner 60 個中文字），英文因此可以寫到兩倍的字元數。
    """

    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in value)


def _check_text(result: ValidationResult, value: Any, path: str, *, max_len: int, required: bool = True) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            result.error("text_missing", f"{path} 必須是非空字串", path)
        return None
    if not _is_text(value):
        result.error("text_type", f"{path} 必須是字串", path)
        return None
    if CONTROL_CHAR_PATTERN.search(value):
        result.error("text_control_char", f"{path} 含有控制字元", path)
    units = text_units(value)
    if units > max_len * 2:
        result.error("text_too_long", f"{path} 超過 {max_len} 個全形字寬（英數以半寬計；目前 {units / 2:g}）", path)
    return value


def _check_id(result: ValidationResult, value: Any, path: str, seen: set[str], kind: str) -> str | None:
    if not _is_text(value) or not ID_PATTERN.match(value):
        result.error("id_invalid", f"{path} 的 id 必須符合 {ID_PATTERN.pattern}", path)
        return None
    if value in seen:
        result.error("id_duplicate", f"{kind} id 重複：{value}", path)
        return None
    seen.add(value)
    return value


def _check_list(result: ValidationResult, value: Any, path: str, bound_key: str) -> list[Any] | None:
    low, high = BOUNDS[bound_key]
    if not isinstance(value, list):
        result.error("list_type", f"{path} 必須是陣列", path)
        return None
    if not low <= len(value) <= high:
        result.error("list_bounds", f"{path} 的長度必須介於 {low} 與 {high}（目前 {len(value)}）", path)
        return None
    return value


def _check_status(result: ValidationResult, value: Any, path: str, *, allow_analogy: bool = True) -> str | None:
    if value not in STATUSES:
        result.error("status_invalid", f"{path} 必須是 {', '.join(STATUSES)} 之一", path)
        return None
    if value == "analogy" and not allow_analogy:
        result.error("status_analogy_forbidden", f"{path} 不可以是 analogy；類比不能當成事實或原因", path)
        return None
    return value


def _check_iso_datetime(value: str) -> bool:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return True


def classify_locator(locator: str) -> str:
    """回傳 url / path / invalid。只有 http(s) URL 與相對 POSIX 路徑可接受。"""

    if URL_PATTERN.match(locator):
        return "url"
    if ABSOLUTE_PATH_PATTERN.match(locator) or "\\" in locator:
        return "invalid"
    if any(part == ".." for part in locator.split("/")):
        return "invalid"
    if LOCAL_PATH_PATTERN.match(locator) and not locator.endswith("/"):
        return "path"
    return "invalid"


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------


def _validate_evidence(result: ValidationResult, spec: dict[str, Any], *, defer_immutable_for_paths: bool = False) -> dict[str, dict[str, Any]]:
    """defer_immutable_for_paths=True 只在 --bind 時使用：本機路徑的不可變識別會由綁定步驟補上，事後再檢查。"""

    entries = _check_list(result, spec.get("evidence"), "evidence", "evidence")
    catalog: dict[str, dict[str, Any]] = {}
    if entries is None:
        return catalog
    seen: set[str] = set()
    for index, item in enumerate(entries):
        path = f"evidence[{index}]"
        if not isinstance(item, dict):
            result.error("evidence_type", f"{path} 必須是物件", path)
            continue
        allowed = {"id", "status", "claim", "locator", "quote", "retrieved_at", "commit_sha", "content_sha256", "line_start", "line_end", "reasoning", "note", "verification"}
        unknown = sorted(set(item) - allowed)
        if unknown:
            result.error("evidence_unknown_field", f"{path} 含未定義欄位：{', '.join(unknown)}", path)
        item_id = _check_id(result, item.get("id"), f"{path}.id", seen, "evidence")
        status = _check_status(result, item.get("status"), f"{path}.status")
        _check_text(result, item.get("claim"), f"{path}.claim", max_len=MAX_LEN["evidence.claim"])
        locator = item.get("locator")
        locator_kind = None
        if locator is not None:
            text = _check_text(result, locator, f"{path}.locator", max_len=MAX_LEN["evidence.locator"])
            if text is not None:
                locator_kind = classify_locator(text)
                if locator_kind == "invalid":
                    result.error(
                        "locator_invalid",
                        f"{path}.locator 只接受 http(s) URL 或相對 POSIX 路徑；絕對路徑、~、.. 與 javascript:/data: 一律拒絕",
                        path,
                    )
        for key in ("quote", "reasoning", "note"):
            if item.get(key) is not None:
                _check_text(result, item.get(key), f"{path}.{key}", max_len=MAX_LEN[f"evidence.{key}"])
        if item.get("retrieved_at") is not None:
            if not _is_text(item["retrieved_at"]) or not _check_iso_datetime(item["retrieved_at"]):
                result.error("retrieved_at_invalid", f"{path}.retrieved_at 必須是 ISO 8601 日期或時間", path)
        if item.get("commit_sha") is not None:
            if not _is_text(item["commit_sha"]) or not COMMIT_PATTERN.match(item["commit_sha"]):
                result.error("commit_sha_invalid", f"{path}.commit_sha 必須是 7 到 64 位小寫十六進位", path)
        if item.get("content_sha256") is not None:
            if not _is_text(item["content_sha256"]) or not SHA256_PATTERN.match(item["content_sha256"]):
                result.error("content_sha256_invalid", f"{path}.content_sha256 必須是 64 位小寫十六進位", path)
        line_start = item.get("line_start")
        line_end = item.get("line_end")
        if (line_start is None) != (line_end is None):
            result.error("line_range_incomplete", f"{path} 的 line_start 與 line_end 必須同時出現", path)
        elif line_start is not None:
            if not (isinstance(line_start, int) and isinstance(line_end, int) and not isinstance(line_start, bool) and not isinstance(line_end, bool)):
                result.error("line_range_type", f"{path} 的 line_start / line_end 必須是整數", path)
            elif line_start < 1 or line_end < line_start:
                result.error("line_range_invalid", f"{path} 的行號範圍必須滿足 1 <= line_start <= line_end", path)
        verification = item.get("verification")
        if verification is not None and verification not in VERIFICATION_LEVELS:
            result.error("verification_invalid", f"{path}.verification 必須是 {', '.join(VERIFICATION_LEVELS)} 之一", path)

        if status == "verified":
            immutable = any(item.get(key) for key in ("commit_sha", "content_sha256", "retrieved_at"))
            if locator is None:
                result.error("verified_locator_missing", f"{path} 是 verified，必須有 locator", path)
            if not item.get("quote"):
                result.error("verified_quote_missing", f"{path} 是 verified，必須有可在來源中找到的短引述 quote", path)
            if not immutable and not (defer_immutable_for_paths and locator_kind == "path"):
                result.error(
                    "verified_immutable_ref_missing",
                    f"{path} 是 verified，必須至少有 commit_sha、content_sha256 或 retrieved_at 之一，否則來源改變後無法察覺",
                    path,
                )
            if locator_kind == "url" and not item.get("retrieved_at"):
                result.error("verified_url_retrieved_at_missing", f"{path} 的 URL 來源必須記錄 retrieved_at", path)
            if verification in ("content-bound", "quote-checked") and not item.get("content_sha256"):
                result.error("verification_claim_unbound", f"{path} 宣告 {verification} 卻沒有 content_sha256", path)
        elif status == "inferred":
            if not item.get("reasoning"):
                result.error("inferred_reasoning_missing", f"{path} 是 inferred，必須寫出推論理由 reasoning", path)
            if verification is not None:
                result.error("verification_not_applicable", f"{path} 不是 verified，不應有 verification 欄位", path)
        elif status == "analogy":
            if verification is not None:
                result.error("verification_not_applicable", f"{path} 不是 verified，不應有 verification 欄位", path)
            if item.get("content_sha256") or item.get("commit_sha"):
                result.warn("analogy_with_immutable_ref", f"{path} 是類比，卻帶有不可變識別；請確認它不是被降級的事實", path)

        if item_id is not None:
            catalog[item_id] = {"status": status, "locator": locator, "locator_kind": locator_kind, "item": item}
    return catalog


def _evidence_refs(result: ValidationResult, refs: Any, path: str, catalog: dict[str, dict[str, Any]], *, status: str | None) -> list[str]:
    if refs is None:
        refs = []
    if not isinstance(refs, list) or not all(_is_text(ref) for ref in refs):
        result.error("evidence_refs_type", f"{path}.evidence 必須是字串陣列", path)
        return []
    if len(refs) != len(set(refs)):
        result.error("evidence_refs_duplicate", f"{path}.evidence 有重複參照", path)
    resolved: list[str] = []
    for ref in refs:
        if ref not in catalog:
            result.error("evidence_ref_missing", f"{path} 參照不存在的 evidence：{ref}", path)
            continue
        resolved.append(ref)
    if status == "verified":
        verified_refs = [ref for ref in resolved if catalog[ref]["status"] == "verified"]
        if not verified_refs:
            result.error("verified_without_verified_evidence", f"{path} 標為 verified，卻沒有引用任何 verified evidence", path)
    return resolved


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------


def _validate_top_level(result: ValidationResult, spec: Any) -> bool:
    if not isinstance(spec, dict):
        result.error("spec_type", "spec 必須是 JSON 物件", "$")
        return False
    unknown = sorted(set(spec) - set(TOP_LEVEL_REQUIRED) - set(TOP_LEVEL_OPTIONAL))
    if unknown:
        result.error("top_level_unknown_field", f"未定義的頂層欄位：{', '.join(unknown)}", "$")
    missing = [key for key in TOP_LEVEL_REQUIRED if key not in spec]
    if missing:
        result.error("top_level_missing_field", f"缺少必要欄位：{', '.join(missing)}", "$")
        return False
    if spec.get("version") != SPEC_VERSION:
        result.error("version_unsupported", f"version 必須是 {SPEC_VERSION}", "version")
    if spec.get("language") not in LANGUAGES:
        result.error("language_unsupported", f"language 必須是 {', '.join(LANGUAGES)} 之一", "language")
    if spec.get("mode") not in MODES:
        result.error("mode_unsupported", f"mode 必須是 {', '.join(MODES)} 之一", "mode")
        return False
    _check_text(result, spec.get("title"), "title", max_len=MAX_LEN["title"])
    _check_text(result, spec.get("audience"), "audience", max_len=MAX_LEN["audience"])
    one_liner = _check_text(result, spec.get("one_liner"), "one_liner", max_len=MAX_LEN["one_liner"])
    if one_liner and "\n" in one_liner:
        result.error("one_liner_multiline", "one_liner 必須是一句話，不可換行", "one_liner")

    analogy = spec.get("analogy")
    if not isinstance(analogy, dict):
        result.error("analogy_type", "analogy 必須是物件，包含 text 與 limits", "analogy")
    else:
        unknown = sorted(set(analogy) - {"text", "limits"})
        if unknown:
            result.error("analogy_unknown_field", f"analogy 含未定義欄位：{', '.join(unknown)}", "analogy")
        _check_text(result, analogy.get("text"), "analogy.text", max_len=MAX_LEN["analogy.text"])
        _check_text(result, analogy.get("limits"), "analogy.limits", max_len=MAX_LEN["analogy.limits"])

    ladder = spec.get("ladder")
    if not isinstance(ladder, dict):
        result.error("ladder_type", "ladder 必須是物件，包含 analogy、truth 與 caveat 三層", "ladder")
    else:
        unknown = sorted(set(ladder) - {"analogy", "truth", "caveat"})
        if unknown:
            result.error("ladder_unknown_field", f"ladder 含未定義欄位：{', '.join(unknown)}", "ladder")
        for key in ("analogy", "truth", "caveat"):
            _check_text(result, ladder.get(key), f"ladder.{key}", max_len=MAX_LEN["ladder"])
    return True


def _validate_scenes(result: ValidationResult, spec: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """回傳 node_id -> {scene, status}。"""

    scenes = _check_list(result, spec.get("scenes"), "scenes", "scenes")
    node_index: dict[str, dict[str, Any]] = {}
    if scenes is None:
        return node_index
    scene_ids: set[str] = set()
    node_ids: set[str] = set()
    for s_index, scene in enumerate(scenes):
        s_path = f"scenes[{s_index}]"
        if not isinstance(scene, dict):
            result.error("scene_type", f"{s_path} 必須是物件", s_path)
            continue
        unknown = sorted(set(scene) - {"id", "title", "caption", "nodes", "edges"})
        if unknown:
            result.error("scene_unknown_field", f"{s_path} 含未定義欄位：{', '.join(unknown)}", s_path)
        scene_id = _check_id(result, scene.get("id"), f"{s_path}.id", scene_ids, "scene")
        _check_text(result, scene.get("title"), f"{s_path}.title", max_len=MAX_LEN["scene.title"])
        _check_text(result, scene.get("caption"), f"{s_path}.caption", max_len=MAX_LEN["scene.caption"])
        nodes = _check_list(result, scene.get("nodes"), f"{s_path}.nodes", "nodes_per_scene")
        local_nodes: set[str] = set()
        if nodes is not None:
            for n_index, node in enumerate(nodes):
                n_path = f"{s_path}.nodes[{n_index}]"
                if not isinstance(node, dict):
                    result.error("node_type", f"{n_path} 必須是物件", n_path)
                    continue
                unknown = sorted(set(node) - {"id", "label", "status", "note", "evidence"})
                if unknown:
                    result.error("node_unknown_field", f"{n_path} 含未定義欄位：{', '.join(unknown)}", n_path)
                node_id = _check_id(result, node.get("id"), f"{n_path}.id", node_ids, "node")
                _check_text(result, node.get("label"), f"{n_path}.label", max_len=MAX_LEN["node.label"])
                if node.get("note") is not None:
                    _check_text(result, node.get("note"), f"{n_path}.note", max_len=MAX_LEN["node.note"])
                status = _check_status(result, node.get("status"), f"{n_path}.status")
                _evidence_refs(result, node.get("evidence"), n_path, catalog, status=status)
                if node_id is not None:
                    local_nodes.add(node_id)
                    node_index[node_id] = {"scene": scene_id, "status": status}
        edges = _check_list(result, scene.get("edges", []), f"{s_path}.edges", "edges_per_scene")
        if edges is not None:
            pairs: set[tuple[str, str]] = set()
            for e_index, edge in enumerate(edges):
                e_path = f"{s_path}.edges[{e_index}]"
                if not isinstance(edge, dict):
                    result.error("edge_type", f"{e_path} 必須是物件", e_path)
                    continue
                unknown = sorted(set(edge) - {"from", "to", "label"})
                if unknown:
                    result.error("edge_unknown_field", f"{e_path} 含未定義欄位：{', '.join(unknown)}", e_path)
                source, target = edge.get("from"), edge.get("to")
                if source not in local_nodes or target not in local_nodes:
                    result.error("edge_ref_missing", f"{e_path} 的 from/to 必須是同一場景內的 node id", e_path)
                    continue
                if source == target:
                    result.error("edge_self_loop", f"{e_path} 不可自我連結", e_path)
                if (source, target) in pairs:
                    result.error("edge_duplicate", f"{e_path} 與其他 edge 重複", e_path)
                pairs.add((source, target))
                if edge.get("label") is not None:
                    _check_text(result, edge.get("label"), f"{e_path}.label", max_len=MAX_LEN["edge.label"])
    return node_index


def _validate_trace(result: ValidationResult, spec: dict[str, Any], node_index: dict[str, dict[str, Any]]) -> None:
    trace = spec.get("trace", [])
    steps = _check_list(result, trace, "trace", "trace")
    if steps is None:
        return
    for index, step in enumerate(steps):
        path = f"trace[{index}]"
        if not isinstance(step, dict):
            result.error("trace_type", f"{path} 必須是物件", path)
            continue
        unknown = sorted(set(step) - {"step", "scene", "node", "text"})
        if unknown:
            result.error("trace_unknown_field", f"{path} 含未定義欄位：{', '.join(unknown)}", path)
        if step.get("step") != index + 1:
            result.error("trace_step_sequence", f"{path}.step 必須是 {index + 1}（從 1 開始連續編號）", path)
        node = step.get("node")
        if node not in node_index:
            result.error("trace_node_missing", f"{path}.node 不存在：{node}", path)
        elif step.get("scene") != node_index[node]["scene"]:
            result.error("trace_scene_mismatch", f"{path}.scene 與 node 所屬場景不符", path)
        _check_text(result, step.get("text"), f"{path}.text", max_len=MAX_LEN["trace.text"])


def _validate_failure_lens(result: ValidationResult, spec: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> None:
    items = _check_list(result, spec.get("failure_lens"), "failure_lens", "failure_lens")
    if items is None:
        return
    seen: set[str] = set()
    for index, item in enumerate(items):
        path = f"failure_lens[{index}]"
        if not isinstance(item, dict):
            result.error("failure_type", f"{path} 必須是物件", path)
            continue
        unknown = sorted(set(item) - {"id", "what_breaks", "symptom", "status", "evidence"})
        if unknown:
            result.error("failure_unknown_field", f"{path} 含未定義欄位：{', '.join(unknown)}", path)
        _check_id(result, item.get("id"), f"{path}.id", seen, "failure_lens")
        _check_text(result, item.get("what_breaks"), f"{path}.what_breaks", max_len=MAX_LEN["failure.what_breaks"])
        _check_text(result, item.get("symptom"), f"{path}.symptom", max_len=MAX_LEN["failure.symptom"])
        status = item.get("status", "inferred")
        status = _check_status(result, status, f"{path}.status", allow_analogy=False)
        _evidence_refs(result, item.get("evidence"), path, catalog, status=status)


def _validate_teach_back(result: ValidationResult, spec: dict[str, Any]) -> None:
    items = _check_list(result, spec.get("teach_back"), "teach_back", "teach_back")
    if items is None:
        return
    for index, item in enumerate(items):
        path = f"teach_back[{index}]"
        if not isinstance(item, dict):
            result.error("teach_type", f"{path} 必須是物件", path)
            continue
        unknown = sorted(set(item) - {"question", "answer"})
        if unknown:
            result.error("teach_unknown_field", f"{path} 含未定義欄位：{', '.join(unknown)}", path)
        _check_text(result, item.get("question"), f"{path}.question", max_len=MAX_LEN["teach.question"])
        _check_text(result, item.get("answer"), f"{path}.answer", max_len=MAX_LEN["teach.answer"])


def _validate_glossary(result: ValidationResult, spec: dict[str, Any]) -> None:
    items = _check_list(result, spec.get("glossary", []), "glossary", "glossary")
    if items is None:
        return
    terms: set[str] = set()
    for index, item in enumerate(items):
        path = f"glossary[{index}]"
        if not isinstance(item, dict):
            result.error("glossary_type", f"{path} 必須是物件", path)
            continue
        unknown = sorted(set(item) - {"term", "plain"})
        if unknown:
            result.error("glossary_unknown_field", f"{path} 含未定義欄位：{', '.join(unknown)}", path)
        term = _check_text(result, item.get("term"), f"{path}.term", max_len=MAX_LEN["glossary.term"])
        _check_text(result, item.get("plain"), f"{path}.plain", max_len=MAX_LEN["glossary.plain"])
        if term is not None:
            if term.lower() in terms:
                result.error("glossary_duplicate", f"{path} 的詞彙重複：{term}", path)
            terms.add(term.lower())


# ---------------------------------------------------------------------------
# story grammar contracts
# ---------------------------------------------------------------------------


def _string_list(result: ValidationResult, value: Any, path: str, *, min_items: int, max_items: int = 12, max_len: int = MAX_LEN["generic"]) -> list[str]:
    if not isinstance(value, list):
        result.error("list_type", f"{path} 必須是字串陣列", path)
        return []
    if not min_items <= len(value) <= max_items:
        result.error("list_bounds", f"{path} 的長度必須介於 {min_items} 與 {max_items}", path)
    items: list[str] = []
    for index, item in enumerate(value):
        text = _check_text(result, item, f"{path}[{index}]", max_len=max_len)
        if text is not None:
            items.append(text)
    return items


def _validate_mode_concept(result: ValidationResult, data: dict[str, Any], catalog: dict[str, dict[str, Any]], node_index: dict[str, dict[str, Any]]) -> None:
    unknown = sorted(set(data) - {"misconceptions"})
    if unknown:
        result.error("mode_data_unknown_field", f"mode_data 含未定義欄位：{', '.join(unknown)}", "mode_data")
    items = _check_list(result, data.get("misconceptions"), "mode_data.misconceptions", "misconceptions")
    if items is None:
        return
    for index, item in enumerate(items):
        path = f"mode_data.misconceptions[{index}]"
        if not isinstance(item, dict) or set(item) - {"myth", "reality"}:
            result.error("misconception_shape", f"{path} 必須只有 myth 與 reality", path)
            continue
        _check_text(result, item.get("myth"), f"{path}.myth", max_len=MAX_LEN["generic"])
        _check_text(result, item.get("reality"), f"{path}.reality", max_len=MAX_LEN["generic"])


def _validate_mode_module(result: ValidationResult, data: dict[str, Any], catalog: dict[str, dict[str, Any]], node_index: dict[str, dict[str, Any]]) -> None:
    unknown = sorted(set(data) - {"source_root", "entry", "exit", "inputs", "outputs"})
    if unknown:
        result.error("mode_data_unknown_field", f"mode_data 含未定義欄位：{', '.join(unknown)}", "mode_data")
    root = _check_text(result, data.get("source_root"), "mode_data.source_root", max_len=MAX_LEN["evidence.locator"])
    if root is not None and classify_locator(root) != "path":
        result.error("source_root_invalid", "mode_data.source_root 必須是相對 POSIX 路徑", "mode_data.source_root")
    for key in ("entry", "exit"):
        node = data.get(key)
        if node not in node_index:
            result.error("module_node_missing", f"mode_data.{key} 必須是存在的 node id", f"mode_data.{key}")
        elif node_index[node]["status"] == "analogy":
            result.error("module_node_analogy", f"mode_data.{key} 指向的 node 不可以是 analogy", f"mode_data.{key}")
    _string_list(result, data.get("inputs"), "mode_data.inputs", min_items=1)
    _string_list(result, data.get("outputs"), "mode_data.outputs", min_items=1)
    local_verified = [entry for entry in catalog.values() if entry["status"] == "verified" and entry["locator_kind"] == "path"]
    if not local_verified:
        result.error("module_local_evidence_missing", "module 模式至少要有一筆 verified evidence 指向本機相對路徑（真的讀過的程式或資料檔）", "evidence")


def _validate_mode_tradeoff(result: ValidationResult, data: dict[str, Any], catalog: dict[str, dict[str, Any]], node_index: dict[str, dict[str, Any]]) -> None:
    unknown = sorted(set(data) - {"options", "decision_rule", "recommendation"})
    if unknown:
        result.error("mode_data_unknown_field", f"mode_data 含未定義欄位：{', '.join(unknown)}", "mode_data")
    options = _check_list(result, data.get("options"), "mode_data.options", "options")
    option_ids: set[str] = set()
    if options is not None:
        for index, option in enumerate(options):
            path = f"mode_data.options[{index}]"
            if not isinstance(option, dict):
                result.error("option_type", f"{path} 必須是物件", path)
                continue
            unknown = sorted(set(option) - {"id", "name", "gains", "costs", "nodes"})
            if unknown:
                result.error("option_unknown_field", f"{path} 含未定義欄位：{', '.join(unknown)}", path)
            _check_id(result, option.get("id"), f"{path}.id", option_ids, "option")
            _check_text(result, option.get("name"), f"{path}.name", max_len=MAX_LEN["glossary.term"])
            _string_list(result, option.get("gains"), f"{path}.gains", min_items=1, max_items=6)
            _string_list(result, option.get("costs"), f"{path}.costs", min_items=1, max_items=6)
            for node in option.get("nodes", []) or []:
                if node not in node_index:
                    result.error("option_node_missing", f"{path}.nodes 參照不存在的 node：{node}", path)
    _check_text(result, data.get("decision_rule"), "mode_data.decision_rule", max_len=MAX_LEN["generic"])
    recommendation = data.get("recommendation")
    if not isinstance(recommendation, dict) or set(recommendation) - {"option", "status", "because", "evidence"}:
        result.error("recommendation_shape", "mode_data.recommendation 必須包含 option、status、because，並可選 evidence", "mode_data.recommendation")
        return
    if recommendation.get("option") not in option_ids:
        result.error("recommendation_option_missing", "mode_data.recommendation.option 必須是 options 內的 id", "mode_data.recommendation")
    status = _check_status(result, recommendation.get("status"), "mode_data.recommendation.status", allow_analogy=False)
    _check_text(result, recommendation.get("because"), "mode_data.recommendation.because", max_len=MAX_LEN["generic"])
    _evidence_refs(result, recommendation.get("evidence"), "mode_data.recommendation", catalog, status=status)


def _validate_mode_incident(result: ValidationResult, data: dict[str, Any], catalog: dict[str, dict[str, Any]], node_index: dict[str, dict[str, Any]]) -> None:
    unknown = sorted(set(data) - {"timeline", "root_cause", "contributing_factors"})
    if unknown:
        result.error("mode_data_unknown_field", f"mode_data 含未定義欄位：{', '.join(unknown)}", "mode_data")
    timeline = _check_list(result, data.get("timeline"), "mode_data.timeline", "timeline")
    if timeline is not None:
        previous: datetime | None = None
        first_break_index: int | None = None
        recovery_after_break = False
        for index, event in enumerate(timeline):
            path = f"mode_data.timeline[{index}]"
            if not isinstance(event, dict):
                result.error("timeline_type", f"{path} 必須是物件", path)
                continue
            unknown = sorted(set(event) - {"t", "event", "kind", "evidence"})
            if unknown:
                result.error("timeline_unknown_field", f"{path} 含未定義欄位：{', '.join(unknown)}", path)
            stamp = event.get("t")
            if not _is_text(stamp) or not _check_iso_datetime(stamp):
                result.error("timeline_time_invalid", f"{path}.t 必須是 ISO 8601 時間", path)
            else:
                candidate = stamp.strip()
                if candidate.endswith("Z"):
                    candidate = candidate[:-1] + "+00:00"
                current = datetime.fromisoformat(candidate)
                if previous is not None:
                    try:
                        out_of_order = current < previous
                    except TypeError:
                        out_of_order = False
                        result.error("timeline_tz_mixed", f"{path}.t 混用了有時區與無時區的時間", path)
                    if out_of_order:
                        result.error("timeline_out_of_order", f"{path}.t 早於前一個事件；時間軸必須由早到晚", path)
                previous = current
            _check_text(result, event.get("event"), f"{path}.event", max_len=MAX_LEN["generic"])
            kind = event.get("kind")
            if kind not in INCIDENT_KINDS:
                result.error("timeline_kind_invalid", f"{path}.kind 必須是 {', '.join(INCIDENT_KINDS)} 之一", path)
            elif kind == "first_break":
                if first_break_index is not None:
                    result.error("timeline_multiple_first_break", "timeline 只能有一個 first_break", path)
                first_break_index = index
            elif kind == "recovery" and first_break_index is not None:
                recovery_after_break = True
            elif kind == "recovery" and first_break_index is None:
                result.error("timeline_recovery_before_break", f"{path} 的 recovery 出現在 first_break 之前", path)
            _evidence_refs(result, event.get("evidence"), path, catalog, status=None)
        if first_break_index is None:
            result.error("timeline_first_break_missing", "incident 模式的 timeline 必須有一個 first_break", "mode_data.timeline")
        elif not recovery_after_break:
            result.error("timeline_recovery_missing", "first_break 之後必須至少有一個 recovery 事件", "mode_data.timeline")
    root_cause = data.get("root_cause")
    if not isinstance(root_cause, dict) or set(root_cause) - {"text", "status", "evidence"}:
        result.error("root_cause_shape", "mode_data.root_cause 必須包含 text、status 與 evidence", "mode_data.root_cause")
    else:
        _check_text(result, root_cause.get("text"), "mode_data.root_cause.text", max_len=MAX_LEN["generic"])
        status = _check_status(result, root_cause.get("status"), "mode_data.root_cause.status", allow_analogy=False)
        refs = _evidence_refs(result, root_cause.get("evidence"), "mode_data.root_cause", catalog, status=status)
        if status == "inferred" and not refs:
            result.warn("root_cause_inferred_without_evidence", "根因是推論且沒有任何 evidence；請在解說中明確說這是假設", "mode_data.root_cause")
    if data.get("contributing_factors") is not None:
        _string_list(result, data.get("contributing_factors"), "mode_data.contributing_factors", min_items=0, max_items=8)


def _validate_mode_metric(result: ValidationResult, data: dict[str, Any], catalog: dict[str, dict[str, Any]], node_index: dict[str, dict[str, Any]]) -> None:
    unknown = sorted(set(data) - {"metric_name", "definition", "lineage", "scope", "comparison"})
    if unknown:
        result.error("mode_data_unknown_field", f"mode_data 含未定義欄位：{', '.join(unknown)}", "mode_data")
    _check_text(result, data.get("metric_name"), "mode_data.metric_name", max_len=MAX_LEN["glossary.term"])
    definition = data.get("definition")
    if not isinstance(definition, dict) or set(definition) - {"text", "status", "evidence"}:
        result.error("definition_shape", "mode_data.definition 必須包含 text、status 與 evidence", "mode_data.definition")
    else:
        _check_text(result, definition.get("text"), "mode_data.definition.text", max_len=MAX_LEN["generic"])
        status = _check_status(result, definition.get("status"), "mode_data.definition.status", allow_analogy=False)
        if status != "verified":
            result.error("definition_not_verified", "指標定義必須是 verified，並引用定義所在的程式、SQL 或文件", "mode_data.definition")
        _evidence_refs(result, definition.get("evidence"), "mode_data.definition", catalog, status=status)
    lineage = _check_list(result, data.get("lineage"), "mode_data.lineage", "lineage")
    if lineage is not None:
        for index, hop in enumerate(lineage):
            path = f"mode_data.lineage[{index}]"
            if not isinstance(hop, dict) or set(hop) - {"from", "to", "transform"}:
                result.error("lineage_shape", f"{path} 必須只有 from、to 與 transform", path)
                continue
            _check_text(result, hop.get("from"), f"{path}.from", max_len=MAX_LEN["generic"])
            _check_text(result, hop.get("to"), f"{path}.to", max_len=MAX_LEN["generic"])
            _check_text(result, hop.get("transform"), f"{path}.transform", max_len=MAX_LEN["generic"])
    scope = data.get("scope")
    if not isinstance(scope, dict) or set(scope) - {"grain", "time_window", "filters"}:
        result.error("scope_shape", "mode_data.scope 必須是包含 grain、time_window、filters 的物件", "mode_data.scope")
    else:
        filled = 0
        for key in ("grain", "time_window", "filters"):
            if scope.get(key):
                filled += 1
                _check_text(result, scope.get(key), f"mode_data.scope.{key}", max_len=MAX_LEN["generic"])
        if filled == 0:
            result.error("scope_empty", "mode_data.scope 至少要說明 grain、time_window 或 filters 其中一項口徑", "mode_data.scope")
    comparison = data.get("comparison")
    if comparison is not None:
        if not isinstance(comparison, dict) or set(comparison) - {"before", "after", "evidence"}:
            result.error("comparison_shape", "mode_data.comparison 必須包含 before、after 與 evidence", "mode_data.comparison")
        else:
            _check_text(result, comparison.get("before"), "mode_data.comparison.before", max_len=MAX_LEN["generic"])
            _check_text(result, comparison.get("after"), "mode_data.comparison.after", max_len=MAX_LEN["generic"])
            refs = _evidence_refs(result, comparison.get("evidence"), "mode_data.comparison", catalog, status=None)
            if not refs:
                result.error("comparison_evidence_missing", "拿數字做前後比較時，before/after 都必須有 evidence", "mode_data.comparison")


MODE_VALIDATORS = {
    "concept": _validate_mode_concept,
    "module": _validate_mode_module,
    "tradeoff": _validate_mode_tradeoff,
    "incident": _validate_mode_incident,
    "metric": _validate_mode_metric,
}


# ---------------------------------------------------------------------------
# provenance checks against local sources
# ---------------------------------------------------------------------------


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def resolve_local_source(source_root: Path, locator: str) -> Path | None:
    """把相對 locator 解析到 source_root 內；逃出邊界回傳 None。"""

    root = source_root.resolve()
    candidate = (root / Path(locator)).resolve()
    if not candidate.is_relative_to(root):
        return None
    return candidate


def check_local_evidence(spec: dict[str, Any], source_root: Path, *, check_quotes: bool, bind: bool, result: ValidationResult) -> None:
    """對本機來源做 content-bound / quote-checked 檢驗；bind=True 時把結果寫回 spec（記憶體內）。"""

    for index, item in enumerate(spec.get("evidence", []) or []):
        if not isinstance(item, dict) or item.get("status") != "verified":
            continue
        path = f"evidence[{index}]"
        locator = item.get("locator")
        if not _is_text(locator):
            continue
        kind = classify_locator(locator)
        if kind == "url":
            level = "structural"
            claimed = item.get("verification")
            if claimed and claimed != "structural":
                result.error("verification_claim_url", f"{path} 是 URL 來源，檢驗等級最多只能是 structural", path)
            elif bind and not claimed:
                item["verification"] = "structural"
            result.verification[str(item.get("id"))] = level
            result.warn("url_not_checked", f"{path} 是 URL 來源，本工具不連網，內容未經比對；請在 retrieved_at 記錄讀取時間", path)
            continue
        if kind != "path":
            continue
        source = resolve_local_source(source_root, locator)
        if source is None:
            result.error("locator_escapes_source_root", f"{path}.locator 逃出 --source-root 的路徑邊界", path)
            continue
        if not source.is_file():
            result.warn("source_not_found", f"{path}.locator 在 --source-root 下找不到檔案，只能維持 structural", path)
            result.verification[str(item.get("id"))] = "structural"
            continue
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        recorded = item.get("content_sha256")
        level = "structural"
        if recorded and recorded != digest:
            result.error("content_sha256_mismatch", f"{path} 的 content_sha256 與目前檔案不符；來源已變更，artifact 不再對應", path)
            result.verification[str(item.get("id"))] = "structural"
            continue
        if bind and not recorded:
            item["content_sha256"] = digest
            recorded = digest
        if recorded == digest:
            level = "content-bound"
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        line_start, line_end = item.get("line_start"), item.get("line_end")
        if isinstance(line_start, int) and isinstance(line_end, int) and not isinstance(line_start, bool):
            if line_end > len(lines):
                result.error("line_range_out_of_file", f"{path} 的 line_end 超過檔案總行數 {len(lines)}", path)
                continue
            haystack = "\n".join(lines[line_start - 1 : line_end])
        else:
            haystack = text
        if check_quotes or bind:
            quote = item.get("quote")
            if _is_text(quote) and _normalize_ws(quote) and _normalize_ws(quote) in _normalize_ws(haystack):
                level = "quote-checked" if level == "content-bound" else level
            else:
                result.error("quote_not_found", f"{path}.quote 沒有出現在來源檔案（或指定行號範圍）內；不可標為 verified", path)
                continue
        claimed = item.get("verification")
        order = {name: rank for rank, name in enumerate(VERIFICATION_LEVELS)}
        if claimed and order.get(claimed, 0) > order[level]:
            if check_quotes or bind:
                result.error("verification_claim_stale", f"{path} 宣告 {claimed}，但本次只能確認到 {level}", path)
            else:
                result.warn("verification_not_rechecked", f"{path} 宣告 {claimed}，本次未加 --check-quotes，只確認到 {level}", path)
        if bind:
            item["verification"] = level
        result.verification[str(item.get("id"))] = level


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def validate_spec(spec: Any, *, source_root: Path | None = None, check_quotes: bool = False, bind: bool = False) -> ValidationResult:
    result = ValidationResult()
    if not _validate_top_level(result, spec):
        return result
    catalog = _validate_evidence(result, spec, defer_immutable_for_paths=bind and source_root is not None)
    node_index = _validate_scenes(result, spec, catalog)
    _validate_trace(result, spec, node_index)
    _validate_failure_lens(result, spec, catalog)
    _validate_teach_back(result, spec)
    _validate_glossary(result, spec)

    statuses = {info["status"] for info in node_index.values()}
    if node_index and statuses <= {"analogy"}:
        result.error("analogy_only", "所有 node 都是 analogy；super-eli5 必須至少有一個 inferred 或 verified 的技術事實", "scenes")

    mode_data = spec.get("mode_data")
    if not isinstance(mode_data, dict):
        result.error("mode_data_type", "mode_data 必須是物件", "mode_data")
    else:
        MODE_VALIDATORS[spec["mode"]](result, mode_data, catalog, node_index)

    referenced: set[str] = set()
    for scene in spec.get("scenes", []) or []:
        for node in (scene.get("nodes", []) if isinstance(scene, dict) else []) or []:
            if isinstance(node, dict):
                referenced.update(ref for ref in (node.get("evidence") or []) if _is_text(ref))
    for item in spec.get("failure_lens", []) or []:
        if isinstance(item, dict):
            referenced.update(ref for ref in (item.get("evidence") or []) if _is_text(ref))
    mode_blob = json.dumps(mode_data, ensure_ascii=False) if isinstance(mode_data, dict) else ""
    for evidence_id, entry in catalog.items():
        if evidence_id not in referenced and f'"{evidence_id}"' not in mode_blob:
            result.warn("evidence_unused", f"evidence {evidence_id} 沒有被任何 node、failure_lens 或 mode_data 引用", f"evidence.{evidence_id}")
        if entry["status"] == "verified" and evidence_id not in result.verification:
            result.verification[evidence_id] = "structural"

    if result.ok and source_root is not None:
        check_local_evidence(spec, source_root, check_quotes=check_quotes, bind=bind, result=result)
        if bind:
            for index, item in enumerate(spec.get("evidence", []) or []):
                if isinstance(item, dict) and item.get("status") == "verified" and not any(item.get(key) for key in ("commit_sha", "content_sha256", "retrieved_at")):
                    result.error("verified_immutable_ref_missing", f"evidence[{index}] 綁定後仍沒有不可變識別；來源檔案不存在或無法讀取", f"evidence[{index}]")
    return result


def configure_stdout() -> None:
    """Windows 重新導向輸出時可能使用 cp950 之類的舊編碼；改成 UTF-8 並以替代字元避免中斷。"""

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def write_json_atomic(path: Path, payload: Any, *, force: bool = False) -> None:
    """no-clobber 寫入：目標存在且未指定 force 就拒絕；不接受 symlink；暫存檔＋原子 os.replace。"""

    target = Path(path)
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file():
            raise FileExistsError(f"拒絕寫入非一般檔案或 symlink：{target}")
        if not force:
            raise FileExistsError(f"目標已存在，未指定 --force 不得覆寫：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".super-eli5-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        try:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(temp_name, 0o666 & ~umask)
        except OSError:
            pass
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="驗證 super-eli5 story spec v1")
    parser.add_argument("spec", help="spec JSON 路徑")
    parser.add_argument("--source-root", type=Path, default=None, help="本機來源根目錄；提供後才會做 content-bound / quote 檢查")
    parser.add_argument("--check-quotes", action="store_true", help="檢查每個 verified quote 是否真的出現在本機來源")
    parser.add_argument("--bind", action="store_true", help="把 content_sha256 與檢驗等級寫回 --out（需要 --source-root）")
    parser.add_argument("--out", type=Path, default=None, help="--bind 的輸出路徑")
    parser.add_argument("--force", action="store_true", help="允許覆寫已存在的 --out")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出結果")
    args = parser.parse_args(argv)
    configure_stdout()

    if args.bind and (args.source_root is None or args.out is None):
        parser.error("--bind 需要同時提供 --source-root 與 --out")

    try:
        spec = load_spec(args.spec)
    except (OSError, ValueError) as exc:
        report = {"validator_version": VALIDATOR_VERSION, "status": "FAIL", "errors": [{"severity": "error", "code": "spec_unreadable", "message": str(exc), "path": args.spec}]}
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"FAIL spec_unreadable: {exc}")
        return 1

    original_sha256 = spec_sha256(spec)
    result = validate_spec(spec, source_root=args.source_root, check_quotes=args.check_quotes, bind=args.bind)
    report = result.as_dict()
    report["spec_sha256"] = original_sha256
    if args.bind and result.ok:
        try:
            write_json_atomic(args.out, spec, force=args.force)
            report["bound_output"] = str(args.out)
            report["bound_spec_sha256"] = spec_sha256(spec)
        except OSError as exc:
            report["status"] = "FAIL"
            report["errors"].append({"severity": "error", "code": "bind_write_failed", "message": str(exc), "path": str(args.out)})
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['status']}  spec_sha256={report['spec_sha256']}  verification={report.get('verification_summary')}")
        for item in report.get("errors", []):
            print(f"  ERROR {item['code']}: {item['message']}")
        for item in report.get("warnings", []):
            print(f"  WARN  {item['code']}: {item['message']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
