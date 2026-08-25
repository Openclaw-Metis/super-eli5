#!/usr/bin/env python3
"""super-eli5 deterministic renderer：story spec v1 → 單檔、離線、零 JavaScript 的 HTML。

設計原則（對應 super-eli5 的證據契約）：
- 同一份 spec 永遠產生 byte-for-byte 相同的 HTML；沒有時間戳、沒有隨機值。
- 輸出不含任何 script、外部資源、inline style 屬性、iframe、form；只有一個 style 區塊。
- Content-Security-Policy 以 style 區塊的 SHA-256 鎖定，瀏覽器會拒絕被竄改的樣式。
- canonical spec JSON 以 HTML escape 內嵌在 pre#super-eli5-spec，並在 meta 記錄 spec SHA-256，
  供 verify_artifact.py 做配對驗證與竄改偵測。
- 證據 URL 允許以連結呈現（讀者可自行點開），本機路徑只以文字呈現，不會被自動讀取。

用法：
  python scripts/render_html.py spec.json out.html
  python scripts/render_html.py spec.json out.html --force            # 明確允許覆寫
  python scripts/render_html.py spec.json out.html --workspace ./out  # 限制輸出只能落在此目錄內

安全邊界：
- 預設 no-clobber：目標存在就拒絕，除非 --force；symlink 與非一般檔案一律拒絕。
- 輸出路徑必須位於 --workspace（預設為目前工作目錄）之內；逃出路徑邊界會被拒絕。
- 寫檔採暫存檔＋原子 os.replace；失敗時舊檔不變，這就是 rollback 路徑。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_spec import canonical_json, classify_locator, configure_stdout, load_spec, spec_sha256, validate_spec  # noqa: E402

RENDERER_VERSION = "1.0.0"
SPEC_PRE_ID = "super-eli5-spec"
META_SPEC_HASH = "super-eli5-spec-sha256"
META_STYLE_HASH = "super-eli5-style-sha256"
META_RENDERER = "super-eli5-renderer"

NODE_W = 200
NODE_H = 64
GAP_X = 40
GAP_Y = 48
MARGIN = 20
COLUMNS = 3
MAX_TRACE_STEPS = 24

LANG_ATTR = {"zh-TW": "zh-Hant", "zh-CN": "zh-Hans", "en": "en"}

UI: dict[str, dict[str, Any]] = {
    "zh-TW": {
        "mode": {"concept": "概念", "module": "模組", "tradeoff": "取捨", "incident": "事故", "metric": "指標"},
        "audience": "對象",
        "language": "語言",
        "l0": "一句話版：五歲也能懂",
        "l1": "一個類比",
        "analogy_limits": "類比在哪裡失真",
        "l2": "三層真相",
        "ladder": {"analogy": "類比", "truth": "技術事實", "caveat": "但要注意"},
        "scenes": "一張圖一個場景",
        "legend": "圖例",
        "status": {"verified": "已驗證", "inferred": "推論", "analogy": "類比"},
        "status_hint": {
            "verified": "有可定位的來源、短引述與不可變識別",
            "inferred": "有理由的推論，尚未被來源直接證實",
            "analogy": "只是幫助理解的比喻，不是事實",
        },
        "evidence_refs": "證據",
        "trace": "流程回放",
        "trace_all": "全部",
        "step": "步驟",
        "failure": "失效鏡頭：什麼時候會壞",
        "what_breaks": "壞掉的地方",
        "symptom": "你會看到的症狀",
        "teach": "教回來：請用自己的話說一次",
        "show_answer": "看參考答案",
        "glossary": "詞彙白話對照",
        "evidence": "證據表",
        "cols": {"id": "編號", "status": "等級", "claim": "主張", "locator": "來源", "quote": "引述", "immutable": "不可變識別", "verification": "檢驗等級", "reasoning": "推論理由"},
        "verification": {"structural": "結構", "content-bound": "內容綁定", "quote-checked": "引述已核對", "none": "未核對"},
        "immutable": {"commit_sha": "commit", "content_sha256": "sha256", "retrieved_at": "讀取於"},
        "concept": {"title": "常見誤解", "myth": "迷思", "reality": "實際上"},
        "module": {"title": "模組邊界", "entry": "入口", "exit": "出口", "inputs": "輸入", "outputs": "輸出", "source_root": "程式根目錄"},
        "tradeoff": {"title": "方案比較", "option": "方案", "gains": "得到", "costs": "付出", "decision_rule": "怎麼選", "recommendation": "建議", "because": "因為"},
        "incident": {"title": "事故時間軸", "kinds": {"normal": "正常", "first_break": "第一次出錯", "detection": "發現", "mitigation": "止血", "recovery": "恢復"}, "root_cause": "根因", "contributing": "促成因素"},
        "metric": {"title": "指標口徑", "definition": "定義", "lineage": "血緣", "grain": "粒度", "time_window": "時間窗", "filters": "篩選", "comparison": "前後比較", "before": "之前", "after": "之後"},
        "generator": "由 super-eli5 renderer 決定性產生",
        "spec_hash": "spec SHA-256",
        "disclaimer": "這是給人審閱的衍生解說，不是權威紀錄。「已驗證」只代表來源可定位、引述對得上且來源版本可識別，不代表來源本身正確。",
    },
    "zh-CN": {
        "mode": {"concept": "概念", "module": "模块", "tradeoff": "取舍", "incident": "事故", "metric": "指标"},
        "audience": "对象",
        "language": "语言",
        "l0": "一句话版：五岁也能懂",
        "l1": "一个类比",
        "analogy_limits": "类比在哪里失真",
        "l2": "三层真相",
        "ladder": {"analogy": "类比", "truth": "技术事实", "caveat": "但要注意"},
        "scenes": "一张图一个场景",
        "legend": "图例",
        "status": {"verified": "已验证", "inferred": "推论", "analogy": "类比"},
        "status_hint": {
            "verified": "有可定位的来源、短引述与不可变标识",
            "inferred": "有理由的推论，尚未被来源直接证实",
            "analogy": "只是帮助理解的比喻，不是事实",
        },
        "evidence_refs": "证据",
        "trace": "流程回放",
        "trace_all": "全部",
        "step": "步骤",
        "failure": "失效镜头：什么时候会坏",
        "what_breaks": "坏掉的地方",
        "symptom": "你会看到的症状",
        "teach": "教回来：请用自己的话说一次",
        "show_answer": "看参考答案",
        "glossary": "词汇白话对照",
        "evidence": "证据表",
        "cols": {"id": "编号", "status": "等级", "claim": "主张", "locator": "来源", "quote": "引述", "immutable": "不可变标识", "verification": "检验等级", "reasoning": "推论理由"},
        "verification": {"structural": "结构", "content-bound": "内容绑定", "quote-checked": "引述已核对", "none": "未核对"},
        "immutable": {"commit_sha": "commit", "content_sha256": "sha256", "retrieved_at": "读取于"},
        "concept": {"title": "常见误解", "myth": "迷思", "reality": "实际上"},
        "module": {"title": "模块边界", "entry": "入口", "exit": "出口", "inputs": "输入", "outputs": "输出", "source_root": "代码根目录"},
        "tradeoff": {"title": "方案比较", "option": "方案", "gains": "得到", "costs": "付出", "decision_rule": "怎么选", "recommendation": "建议", "because": "因为"},
        "incident": {"title": "事故时间轴", "kinds": {"normal": "正常", "first_break": "第一次出错", "detection": "发现", "mitigation": "止血", "recovery": "恢复"}, "root_cause": "根因", "contributing": "促成因素"},
        "metric": {"title": "指标口径", "definition": "定义", "lineage": "血缘", "grain": "粒度", "time_window": "时间窗", "filters": "筛选", "comparison": "前后比较", "before": "之前", "after": "之后"},
        "generator": "由 super-eli5 renderer 确定性生成",
        "spec_hash": "spec SHA-256",
        "disclaimer": "这是给人审阅的衍生解说，不是权威记录。「已验证」只代表来源可定位、引述对得上且来源版本可识别，不代表来源本身正确。",
    },
    "en": {
        "mode": {"concept": "Concept", "module": "Module", "tradeoff": "Tradeoff", "incident": "Incident", "metric": "Metric"},
        "audience": "Audience",
        "language": "Language",
        "l0": "One sentence a five-year-old gets",
        "l1": "One analogy",
        "analogy_limits": "Where the analogy breaks",
        "l2": "Three layers of truth",
        "ladder": {"analogy": "Analogy", "truth": "Technical truth", "caveat": "Watch out"},
        "scenes": "One picture per scene",
        "legend": "Legend",
        "status": {"verified": "Verified", "inferred": "Inferred", "analogy": "Analogy"},
        "status_hint": {
            "verified": "Has a locatable source, a short quote and an immutable reference",
            "inferred": "Reasoned but not directly confirmed by a source",
            "analogy": "A helpful comparison, not a fact",
        },
        "evidence_refs": "Evidence",
        "trace": "Trace playback",
        "trace_all": "All",
        "step": "Step",
        "failure": "Failure lens: when it breaks",
        "what_breaks": "What breaks",
        "symptom": "What you would see",
        "teach": "Teach it back in your own words",
        "show_answer": "Show a reference answer",
        "glossary": "Plain-language glossary",
        "evidence": "Evidence table",
        "cols": {"id": "ID", "status": "Status", "claim": "Claim", "locator": "Source", "quote": "Quote", "immutable": "Immutable ref", "verification": "Check level", "reasoning": "Reasoning"},
        "verification": {"structural": "structural", "content-bound": "content-bound", "quote-checked": "quote-checked", "none": "not checked"},
        "immutable": {"commit_sha": "commit", "content_sha256": "sha256", "retrieved_at": "retrieved"},
        "concept": {"title": "Common misconceptions", "myth": "Myth", "reality": "Reality"},
        "module": {"title": "Module boundary", "entry": "Entry", "exit": "Exit", "inputs": "Inputs", "outputs": "Outputs", "source_root": "Source root"},
        "tradeoff": {"title": "Option comparison", "option": "Option", "gains": "Gains", "costs": "Costs", "decision_rule": "How to choose", "recommendation": "Recommendation", "because": "Because"},
        "incident": {"title": "Incident timeline", "kinds": {"normal": "normal", "first_break": "first break", "detection": "detection", "mitigation": "mitigation", "recovery": "recovery"}, "root_cause": "Root cause", "contributing": "Contributing factors"},
        "metric": {"title": "Metric definition and scope", "definition": "Definition", "lineage": "Lineage", "grain": "Grain", "time_window": "Time window", "filters": "Filters", "comparison": "Before and after", "before": "Before", "after": "After"},
        "generator": "Deterministically generated by the super-eli5 renderer",
        "spec_hash": "spec SHA-256",
        "disclaimer": "This is a human-reviewable derived explanation, not an authoritative record. \"Verified\" means the source is locatable, the quote matches and the source version is identifiable; it does not mean the source itself is correct.",
    },
}

_BASE_CSS = """
:root{--ink:#1d1f24;--muted:#5c6470;--bg:#fbfaf7;--card:#ffffff;--line:#e3e0d8;--verified:#1b7f3b;--verified-bg:#e7f5ea;--inferred:#b45f06;--inferred-bg:#fff3e0;--analogy:#6a3fb5;--analogy-bg:#f1ebfb;--accent:#0b5fa5}
*{box-sizing:border-box}
html{font-size:16px}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.6}
main.eli5{max-width:960px;margin:0 auto;padding:24px 16px 48px}
header.top{border-bottom:2px solid var(--line);padding-bottom:12px;margin-bottom:20px}
header.top h1{font-size:1.75rem;margin:8px 0 4px;line-height:1.3}
.badges{display:flex;flex-wrap:wrap;gap:8px;font-size:.85rem}
.badge{border:1px solid var(--line);border-radius:999px;padding:2px 10px;background:var(--card);color:var(--muted)}
.badge.mode{background:var(--accent);color:#fff;border-color:var(--accent)}
section{margin:28px 0}
section h2{font-size:1.2rem;margin:0 0 10px;padding-left:10px;border-left:4px solid var(--accent)}
section h3{font-size:1.05rem;margin:18px 0 6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.one-liner{font-size:1.5rem;font-weight:600;line-height:1.5;margin:0}
.analogy .limits{margin-top:10px;color:var(--muted);font-size:.95rem}
.ladder{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.ladder .rung{border-top:6px solid var(--line)}
.ladder .rung.analogy{border-top-color:var(--analogy)}
.ladder .rung.truth{border-top-color:var(--verified)}
.ladder .rung.caveat{border-top-color:var(--inferred)}
.ladder .rung h3{margin:0 0 6px;font-size:.95rem;color:var(--muted)}
.ladder .rung p{margin:0}
.legend{display:flex;flex-wrap:wrap;gap:10px 18px;font-size:.85rem;color:var(--muted);margin:8px 0 14px}
.legend .swatch{display:inline-block;width:14px;height:14px;border-radius:4px;vertical-align:-2px;margin-right:6px;border:2px solid}
.legend .swatch.verified{background:var(--verified-bg);border-color:var(--verified)}
.legend .swatch.inferred{background:var(--inferred-bg);border-color:var(--inferred);border-style:dashed}
.legend .swatch.analogy{background:var(--analogy-bg);border-color:var(--analogy);border-style:dotted}
.scene{margin-bottom:22px}
.scene .caption{color:var(--muted);margin:0 0 10px}
.scene svg{width:100%;height:auto;display:block;background:var(--card);border:1px solid var(--line);border-radius:12px}
svg .node{stroke-width:2}
svg .node.verified{fill:var(--verified-bg);stroke:var(--verified)}
svg .node.inferred{fill:var(--inferred-bg);stroke:var(--inferred);stroke-dasharray:6 4}
svg .node.analogy{fill:var(--analogy-bg);stroke:var(--analogy);stroke-dasharray:2 4}
svg .label{font-size:14px;fill:var(--ink);text-anchor:middle;font-weight:600}
svg .status{font-size:10px;fill:var(--muted)}
svg .edge{stroke:#7a8290;stroke-width:1.8;fill:none}
svg .edge-label{font-size:11px;fill:var(--muted);text-anchor:middle;paint-order:stroke;stroke:#fff;stroke-width:4px}
svg .arrow{fill:#7a8290}
.nodes{list-style:none;padding:0;margin:10px 0 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.nodes li{background:var(--card);border:1px solid var(--line);border-left-width:6px;border-radius:10px;padding:10px 12px;font-size:.95rem}
.nodes li.verified{border-left-color:var(--verified)}
.nodes li.inferred{border-left-color:var(--inferred)}
.nodes li.analogy{border-left-color:var(--analogy)}
.nodes .status-tag{font-size:.75rem;color:var(--muted);margin-left:6px}
.nodes .note{margin:4px 0 0;color:var(--muted)}
.nodes .refs{margin:4px 0 0;font-size:.8rem;color:var(--accent)}
.player{position:relative;display:flex;flex-wrap:wrap;gap:6px}
.player input{position:absolute;opacity:0;pointer-events:none;width:1px;height:1px}
.player label{cursor:pointer;border:1px solid var(--line);border-radius:8px;padding:2px 10px;background:var(--card);font-size:.9rem;user-select:none}
.player .steps{flex:1 1 100%;margin-top:6px}
.player input:checked+label{background:var(--accent);color:#fff;border-color:var(--accent)}
.player input:focus-visible+label{outline:3px solid var(--accent);outline-offset:2px}
.steps{margin:0;padding-left:22px}
.steps .step{padding:6px 8px;border-radius:8px;margin:4px 0}
.steps .step .where{font-size:.8rem;color:var(--muted);margin-left:6px}
.failure ul,.teach ul,.mode-panel ul{padding-left:20px}
.failure li{margin:8px 0}
.failure .symptom{color:var(--muted)}
.teach details{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:8px 0}
.teach summary{cursor:pointer;font-weight:600}
.teach details p{margin:8px 0 0}
dl.glossary{display:grid;grid-template-columns:max-content 1fr;gap:6px 16px;margin:0}
dl.glossary dt{font-weight:600}
dl.glossary dd{margin:0;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:.88rem;background:var(--card)}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f3f1ec}
td.status-verified{color:var(--verified);font-weight:600}
td.status-inferred{color:var(--inferred);font-weight:600}
td.status-analogy{color:var(--analogy);font-weight:600}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.85em;background:#f3f1ec;padding:1px 4px;border-radius:4px;word-break:break-all}
.timeline{list-style:none;padding:0;margin:0}
.timeline li{padding:6px 0 6px 14px;border-left:3px solid var(--line)}
.timeline li.first_break{border-left-color:#c62828}
.timeline li.detection{border-left-color:var(--inferred)}
.timeline li.mitigation{border-left-color:var(--accent)}
.timeline li.recovery{border-left-color:var(--verified)}
.timeline time{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85rem;color:var(--muted);margin-right:8px}
.kind{font-size:.75rem;border-radius:999px;padding:1px 8px;background:#f3f1ec;color:var(--muted);margin-right:6px}
.lineage{list-style:none;padding:0;margin:0}
.lineage li{padding:4px 0}
.lineage .arrow{color:var(--muted);margin:0 8px}
footer.bottom{margin-top:36px;border-top:1px solid var(--line);padding-top:12px;font-size:.82rem;color:var(--muted)}
footer.bottom p{margin:4px 0}
a{color:var(--accent)}
@media (max-width:640px){.ladder{grid-template-columns:1fr}header.top h1{font-size:1.4rem}.one-liner{font-size:1.25rem}dl.glossary{grid-template-columns:1fr}table{font-size:.8rem}}
@media print{.player label{display:none}.teach details{page-break-inside:avoid}}
"""


def _trace_css() -> str:
    rules = []
    for step in range(1, MAX_TRACE_STEPS + 1):
        rules.append(f".player #trace-{step}:checked~.steps .step{{opacity:.45}}")
        rules.append(f".player #trace-{step}:checked~.steps .step:nth-child({step}){{opacity:1;background:#e9f2fb;outline:2px solid var(--accent)}}")
    return "\n".join(rules)


CSS = _BASE_CSS.strip() + "\n" + _trace_css() + "\n"
STYLE_SHA256_HEX = hashlib.sha256(CSS.encode("utf-8")).hexdigest()
STYLE_SHA256_B64 = base64.b64encode(hashlib.sha256(CSS.encode("utf-8")).digest()).decode("ascii")
CSP = f"default-src 'none'; style-src 'sha256-{STYLE_SHA256_B64}'; base-uri 'none'; form-action 'none'"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def wrap_label(text: str, *, max_units: int = 24, max_lines: int = 3) -> list[str]:
    """把節點標籤切成最多 max_lines 行；CJK 逐字可斷，拉丁字母以空白分詞，原有空白會保留。"""

    tokens: list[tuple[str, bool]] = []
    current = ""
    pending_space = False
    for ch in text:
        if ch.isspace():
            if current:
                tokens.append((current, pending_space))
                current = ""
            pending_space = True
            continue
        if _width(ch) == 2:
            if current:
                tokens.append((current, pending_space))
                current = ""
                pending_space = False
            tokens.append((ch, pending_space))
            pending_space = False
        else:
            current += ch
    if current:
        tokens.append((current, pending_space))

    split_tokens: list[tuple[str, bool]] = []
    for token, space_before in tokens:
        while sum(_width(c) for c in token) > max_units:
            split_tokens.append((token[:max_units], space_before))
            token, space_before = token[max_units:], False
        split_tokens.append((token, space_before))
    tokens = split_tokens

    lines: list[str] = []
    line = ""
    for token, space_before in tokens:
        joiner = " " if line and space_before else ""
        candidate = line + joiner + token
        if line and sum(_width(c) for c in candidate) > max_units:
            lines.append(line)
            line = token
        else:
            line = candidate
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [lines[max_lines - 1] + "…"]
    return lines or [""]


def _fmt(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _anchor(cx: float, cy: float, dx: float, dy: float) -> tuple[float, float]:
    """從矩形中心沿 (dx, dy) 射線走到矩形邊界。"""

    if dx == 0 and dy == 0:
        return cx, cy
    half_w, half_h = NODE_W / 2, NODE_H / 2
    scale_x = half_w / abs(dx) if dx else float("inf")
    scale_y = half_h / abs(dy) if dy else float("inf")
    scale = min(scale_x, scale_y)
    return cx + dx * scale, cy + dy * scale


def _node_position(index: int) -> tuple[int, int]:
    col, row = index % COLUMNS, index // COLUMNS
    return MARGIN + col * (NODE_W + GAP_X), MARGIN + row * (NODE_H + GAP_Y)


def _render_scene_svg(scene: dict[str, Any], ui: dict[str, Any]) -> str:
    nodes = scene.get("nodes", [])
    count = len(nodes)
    cols = min(count, COLUMNS)
    rows = (count + COLUMNS - 1) // COLUMNS
    width = MARGIN * 2 + cols * NODE_W + (cols - 1) * GAP_X
    height = MARGIN * 2 + rows * NODE_H + (rows - 1) * GAP_Y
    marker_id = f"arrow-{scene['id']}"
    centers: dict[str, tuple[float, float]] = {}
    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="{esc(scene["id"])}-title" xmlns="http://www.w3.org/2000/svg">',
        f'<title id="{esc(scene["id"])}-title">{esc(scene.get("title"))}</title>',
        f'<defs><marker id="{esc(marker_id)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path class="arrow" d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>',
    ]
    for index, node in enumerate(nodes):
        x, y = _node_position(index)
        centers[node["id"]] = (x + NODE_W / 2, y + NODE_H / 2)
    for edge in scene.get("edges", []) or []:
        (x1, y1), (x2, y2) = centers[edge["from"]], centers[edge["to"]]
        dx, dy = x2 - x1, y2 - y1
        sx, sy = _anchor(x1, y1, dx, dy)
        tx, ty = _anchor(x2, y2, -dx, -dy)
        parts.append(f'<line class="edge" x1="{_fmt(sx)}" y1="{_fmt(sy)}" x2="{_fmt(tx)}" y2="{_fmt(ty)}" marker-end="url(#{esc(marker_id)})"/>')
        if edge.get("label"):
            parts.append(f'<text class="edge-label" x="{_fmt((sx + tx) / 2)}" y="{_fmt((sy + ty) / 2 - 6)}">{esc(edge["label"])}</text>')
    for index, node in enumerate(nodes):
        x, y = _node_position(index)
        status = node.get("status", "inferred")
        lines = wrap_label(str(node.get("label", "")))
        parts.append(f'<rect class="node {esc(status)}" x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="10"/>')
        parts.append(f'<text class="status" x="{x + 8}" y="{y + 13}">{esc(ui["status"][status])}</text>')
        base_y = y + NODE_H / 2 + 5 - (len(lines) - 1) * 8
        for line_index, line in enumerate(lines):
            parts.append(f'<text class="label" x="{_fmt(x + NODE_W / 2)}" y="{_fmt(base_y + line_index * 16)}">{esc(line)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _evidence_map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in spec.get("evidence", [])}


def _refs_html(refs: list[str] | None, ui: dict[str, Any]) -> str:
    if not refs:
        return ""
    links = ", ".join(f'<a href="#ev-{esc(ref)}">{esc(ref)}</a>' for ref in refs)
    return f'<p class="refs">{esc(ui["evidence_refs"])}: {links}</p>'


def _status_tag(status: str, ui: dict[str, Any]) -> str:
    return f'<span class="status-tag">[{esc(ui["status"][status])}]</span>'


def _locator_html(locator: str | None) -> str:
    if not locator:
        return ""
    if classify_locator(locator) == "url":
        return f'<a href="{esc(locator)}" rel="noopener noreferrer">{esc(locator)}</a>'
    return f"<code>{esc(locator)}</code>"


def _immutable_html(item: dict[str, Any], ui: dict[str, Any]) -> str:
    bits: list[str] = []
    if item.get("commit_sha"):
        bits.append(f'{esc(ui["immutable"]["commit_sha"])} <code>{esc(item["commit_sha"][:12])}</code>')
    if item.get("content_sha256"):
        bits.append(f'{esc(ui["immutable"]["content_sha256"])} <code>{esc(item["content_sha256"][:12])}…</code>')
    if item.get("retrieved_at"):
        bits.append(f'{esc(ui["immutable"]["retrieved_at"])} {esc(item["retrieved_at"])}')
    if item.get("line_start"):
        bits.append(f'L{esc(item["line_start"])}-L{esc(item["line_end"])}')
    return "<br>".join(bits)


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------


def _render_header(spec: dict[str, Any], ui: dict[str, Any]) -> str:
    return "\n".join(
        [
            '<header class="top">',
            '<div class="badges">',
            f'<span class="badge mode">{esc(ui["mode"][spec["mode"]])}</span>',
            f'<span class="badge">{esc(ui["audience"])}: {esc(spec["audience"])}</span>',
            f'<span class="badge">{esc(ui["language"])}: {esc(spec["language"])}</span>',
            "</div>",
            f"<h1>{esc(spec['title'])}</h1>",
            "</header>",
        ]
    )


def _render_l0_l1_l2(spec: dict[str, Any], ui: dict[str, Any]) -> str:
    ladder = spec["ladder"]
    analogy = spec["analogy"]
    return "\n".join(
        [
            '<section class="l0">',
            f'<h2>{esc(ui["l0"])}</h2>',
            f'<div class="card"><p class="one-liner">{esc(spec["one_liner"])}</p></div>',
            "</section>",
            '<section class="analogy">',
            f'<h2>{esc(ui["l1"])}</h2>',
            f'<div class="card"><p>{esc(analogy["text"])}</p><p class="limits"><strong>{esc(ui["analogy_limits"])}:</strong> {esc(analogy["limits"])}</p></div>',
            "</section>",
            '<section class="l2">',
            f'<h2>{esc(ui["l2"])}</h2>',
            '<div class="ladder">',
            f'<div class="card rung analogy"><h3>{esc(ui["ladder"]["analogy"])}</h3><p>{esc(ladder["analogy"])}</p></div>',
            f'<div class="card rung truth"><h3>{esc(ui["ladder"]["truth"])}</h3><p>{esc(ladder["truth"])}</p></div>',
            f'<div class="card rung caveat"><h3>{esc(ui["ladder"]["caveat"])}</h3><p>{esc(ladder["caveat"])}</p></div>',
            "</div>",
            "</section>",
        ]
    )


def _render_scenes(spec: dict[str, Any], ui: dict[str, Any]) -> str:
    parts = ['<section class="scenes">', f'<h2>{esc(ui["scenes"])}</h2>', '<div class="legend">']
    for status in ("verified", "inferred", "analogy"):
        parts.append(f'<span><span class="swatch {status}"></span>{esc(ui["status"][status])}: {esc(ui["status_hint"][status])}</span>')
    parts.append("</div>")
    for scene in spec["scenes"]:
        parts.append(f'<article class="scene" id="scene-{esc(scene["id"])}">')
        parts.append(f"<h3>{esc(scene['title'])}</h3>")
        parts.append(f'<p class="caption">{esc(scene["caption"])}</p>')
        parts.append(_render_scene_svg(scene, ui))
        parts.append('<ul class="nodes">')
        for node in scene["nodes"]:
            status = node.get("status", "inferred")
            parts.append(f'<li class="{esc(status)}" id="node-{esc(node["id"])}"><strong>{esc(node["label"])}</strong>{_status_tag(status, ui)}')
            if node.get("note"):
                parts.append(f'<p class="note">{esc(node["note"])}</p>')
            parts.append(_refs_html(node.get("evidence"), ui))
            parts.append("</li>")
        parts.append("</ul>")
        parts.append("</article>")
    parts.append("</section>")
    return "\n".join(parts)


def _render_trace(spec: dict[str, Any], ui: dict[str, Any]) -> str:
    trace = spec.get("trace") or []
    if not trace:
        return ""
    parts = ['<section class="trace">', f'<h2>{esc(ui["trace"])}</h2>', '<div class="player">']
    parts.append(f'<input type="radio" name="trace" id="trace-0" checked><label for="trace-0">{esc(ui["trace_all"])}</label>')
    for step in trace:
        parts.append(f'<input type="radio" name="trace" id="trace-{step["step"]}"><label for="trace-{step["step"]}">{step["step"]}</label>')
    parts.append('<ol class="steps">')
    for step in trace:
        parts.append(f'<li class="step">{esc(step["text"])}<span class="where">#{esc(step["scene"])} / {esc(step["node"])}</span></li>')
    parts.append("</ol>")
    parts.append("</div></section>")
    return "\n".join(parts)


def _render_failure(spec: dict[str, Any], ui: dict[str, Any]) -> str:
    parts = ['<section class="failure">', f'<h2>{esc(ui["failure"])}</h2>', "<ul>"]
    for item in spec["failure_lens"]:
        status = item.get("status", "inferred")
        parts.append(f'<li id="fail-{esc(item["id"])}"><strong>{esc(ui["what_breaks"])}:</strong> {esc(item["what_breaks"])}{_status_tag(status, ui)}<br><span class="symptom"><strong>{esc(ui["symptom"])}:</strong> {esc(item["symptom"])}</span>{_refs_html(item.get("evidence"), ui)}</li>')
    parts.append("</ul></section>")
    return "\n".join(parts)


def _render_teach(spec: dict[str, Any], ui: dict[str, Any]) -> str:
    parts = ['<section class="teach">', f'<h2>{esc(ui["teach"])}</h2>']
    for item in spec["teach_back"]:
        parts.append(f'<details><summary>{esc(item["question"])}</summary><p>{esc(item["answer"])}</p></details>')
    parts.append("</section>")
    return "\n".join(parts)


def _render_glossary(spec: dict[str, Any], ui: dict[str, Any]) -> str:
    glossary = spec.get("glossary") or []
    if not glossary:
        return ""
    parts = ['<section class="glossary">', f'<h2>{esc(ui["glossary"])}</h2>', '<div class="card"><dl class="glossary">']
    for item in glossary:
        parts.append(f"<dt>{esc(item['term'])}</dt><dd>{esc(item['plain'])}</dd>")
    parts.append("</dl></div></section>")
    return "\n".join(parts)


def _render_mode_panel(spec: dict[str, Any], ui: dict[str, Any]) -> str:
    mode = spec["mode"]
    data = spec["mode_data"]
    labels = ui[mode]
    parts = [f'<section class="mode-panel {esc(mode)}">', f'<h2>{esc(labels["title"])}</h2>', '<div class="card">']
    if mode == "concept":
        parts.append("<ul>")
        for item in data["misconceptions"]:
            parts.append(f'<li><strong>{esc(labels["myth"])}:</strong> {esc(item["myth"])}<br><strong>{esc(labels["reality"])}:</strong> {esc(item["reality"])}</li>')
        parts.append("</ul>")
    elif mode == "module":
        parts.append(f'<p><strong>{esc(labels["source_root"])}:</strong> <code>{esc(data["source_root"])}</code></p>')
        parts.append(f'<p><strong>{esc(labels["entry"])}:</strong> <a href="#node-{esc(data["entry"])}">{esc(data["entry"])}</a> · <strong>{esc(labels["exit"])}:</strong> <a href="#node-{esc(data["exit"])}">{esc(data["exit"])}</a></p>')
        parts.append(f'<p><strong>{esc(labels["inputs"])}:</strong></p><ul>' + "".join(f"<li>{esc(x)}</li>" for x in data["inputs"]) + "</ul>")
        parts.append(f'<p><strong>{esc(labels["outputs"])}:</strong></p><ul>' + "".join(f"<li>{esc(x)}</li>" for x in data["outputs"]) + "</ul>")
    elif mode == "tradeoff":
        parts.append(f'<table><thead><tr><th>{esc(labels["option"])}</th><th>{esc(labels["gains"])}</th><th>{esc(labels["costs"])}</th></tr></thead><tbody>')
        for option in data["options"]:
            gains = "<br>".join(esc(x) for x in option["gains"])
            costs = "<br>".join(esc(x) for x in option["costs"])
            parts.append(f'<tr><td><strong>{esc(option["name"])}</strong></td><td>{gains}</td><td>{costs}</td></tr>')
        parts.append("</tbody></table>")
        parts.append(f'<p><strong>{esc(labels["decision_rule"])}:</strong> {esc(data["decision_rule"])}</p>')
        rec = data["recommendation"]
        name = next((o["name"] for o in data["options"] if o["id"] == rec["option"]), rec["option"])
        parts.append(f'<p><strong>{esc(labels["recommendation"])}:</strong> {esc(name)}{_status_tag(rec["status"], ui)}<br><strong>{esc(labels["because"])}:</strong> {esc(rec["because"])}</p>{_refs_html(rec.get("evidence"), ui)}')
    elif mode == "incident":
        parts.append('<ol class="timeline">')
        for event in data["timeline"]:
            parts.append(f'<li class="{esc(event["kind"])}"><time>{esc(event["t"])}</time><span class="kind">{esc(labels["kinds"][event["kind"]])}</span>{esc(event["event"])}{_refs_html(event.get("evidence"), ui)}</li>')
        parts.append("</ol>")
        root = data["root_cause"]
        parts.append(f'<p><strong>{esc(labels["root_cause"])}:</strong> {esc(root["text"])}{_status_tag(root["status"], ui)}</p>{_refs_html(root.get("evidence"), ui)}')
        if data.get("contributing_factors"):
            parts.append(f'<p><strong>{esc(labels["contributing"])}:</strong></p><ul>' + "".join(f"<li>{esc(x)}</li>" for x in data["contributing_factors"]) + "</ul>")
    elif mode == "metric":
        definition = data["definition"]
        parts.append(f'<p><strong>{esc(data["metric_name"])}</strong></p>')
        parts.append(f'<p><strong>{esc(labels["definition"])}:</strong> {esc(definition["text"])}{_status_tag(definition["status"], ui)}</p>{_refs_html(definition.get("evidence"), ui)}')
        parts.append(f'<p><strong>{esc(labels["lineage"])}:</strong></p><ol class="lineage">')
        for hop in data["lineage"]:
            parts.append(f'<li><code>{esc(hop["from"])}</code><span class="arrow">→</span><code>{esc(hop["to"])}</code>: {esc(hop["transform"])}</li>')
        parts.append("</ol>")
        scope = data["scope"]
        scope_bits = [f'<strong>{esc(labels[key])}:</strong> {esc(scope[key])}' for key in ("grain", "time_window", "filters") if scope.get(key)]
        parts.append("<p>" + " · ".join(scope_bits) + "</p>")
        if data.get("comparison"):
            comparison = data["comparison"]
            parts.append(f'<p><strong>{esc(labels["comparison"])}:</strong> {esc(labels["before"])} {esc(comparison["before"])} → {esc(labels["after"])} {esc(comparison["after"])}</p>{_refs_html(comparison.get("evidence"), ui)}')
    parts.append("</div></section>")
    return "\n".join(parts)


def _render_evidence(spec: dict[str, Any], ui: dict[str, Any]) -> str:
    cols = ui["cols"]
    parts = [
        '<section class="evidence">',
        f'<h2>{esc(ui["evidence"])}</h2>',
        "<table><thead><tr>"
        + "".join(f"<th>{esc(cols[key])}</th>" for key in ("id", "status", "claim", "locator", "quote", "immutable", "verification"))
        + "</tr></thead><tbody>",
    ]
    for item in spec["evidence"]:
        status = item["status"]
        quote_or_reason = item.get("quote") if status == "verified" else item.get("reasoning") or item.get("note") or ""
        level = item.get("verification") if status == "verified" else None
        level_text = ui["verification"][level] if level else ("" if status != "verified" else ui["verification"]["none"])
        parts.append(
            f'<tr id="ev-{esc(item["id"])}"><td><code>{esc(item["id"])}</code></td><td class="status-{esc(status)}">{esc(ui["status"][status])}</td>'
            f'<td>{esc(item["claim"])}</td><td>{_locator_html(item.get("locator"))}</td><td>{esc(quote_or_reason)}</td>'
            f'<td>{_immutable_html(item, ui)}</td><td>{esc(level_text)}</td></tr>'
        )
    parts.append("</tbody></table></section>")
    return "\n".join(parts)


def _render_footer(spec_hash: str, ui: dict[str, Any]) -> str:
    return "\n".join(
        [
            '<footer class="bottom">',
            f'<p>{esc(ui["generator"])} {esc(RENDERER_VERSION)}</p>',
            f'<p>{esc(ui["spec_hash"])}: <code>{esc(spec_hash)}</code></p>',
            f'<p>{esc(ui["disclaimer"])}</p>',
            "</footer>",
        ]
    )


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def render(spec: dict[str, Any]) -> str:
    """把已驗證的 spec 決定性地編譯成單檔 HTML 字串。"""

    ui = UI[spec["language"]]
    canonical = canonical_json(spec)
    spec_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    head = "\n".join(
        [
            "<!DOCTYPE html>",
            f'<html lang="{LANG_ATTR[spec["language"]]}">',
            "<head>",
            '<meta charset="utf-8">',
            f'<meta http-equiv="Content-Security-Policy" content="{CSP}">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            '<meta name="referrer" content="no-referrer">',
            f'<meta name="{META_RENDERER}" content="{RENDERER_VERSION}">',
            f'<meta name="{META_SPEC_HASH}" content="{spec_hash}">',
            f'<meta name="{META_STYLE_HASH}" content="{STYLE_SHA256_HEX}">',
            f"<title>{esc(spec['title'])}</title>",
            f"<style>{CSS}</style>",
            "</head>",
        ]
    )
    body = "\n".join(
        part
        for part in [
            "<body>",
            '<main class="eli5">',
            _render_header(spec, ui),
            _render_l0_l1_l2(spec, ui),
            _render_scenes(spec, ui),
            _render_trace(spec, ui),
            _render_failure(spec, ui),
            _render_teach(spec, ui),
            _render_glossary(spec, ui),
            _render_mode_panel(spec, ui),
            _render_evidence(spec, ui),
            _render_footer(spec_hash, ui),
            "</main>",
            f'<pre hidden id="{SPEC_PRE_ID}">{esc(canonical)}</pre>',
            "</body>",
            "</html>",
        ]
        if part
    )
    return head + "\n" + body + "\n"


def _apply_default_mode(path: str) -> None:
    """mkstemp 預設 0600；改回符合 umask 的一般檔案權限，讓輸出可被其他人閱讀。"""

    try:
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(path, 0o666 & ~umask)
    except OSError:
        pass


def write_text_atomic(target: Path, text: str, *, force: bool, workspace: Path) -> None:
    """輸出必須在 workspace 路徑邊界內；no-clobber；拒絕 symlink；暫存檔＋原子 os.replace。"""

    root = workspace.resolve()
    resolved_parent = target.parent.resolve()
    if not resolved_parent.is_relative_to(root):
        raise PermissionError(f"輸出路徑逃出 --workspace 邊界：{target}")
    if target.is_symlink():
        raise FileExistsError(f"拒絕寫入 symlink：{target}")
    if target.exists():
        if not target.is_file():
            raise FileExistsError(f"拒絕寫入非一般檔案：{target}")
        if not force:
            raise FileExistsError(f"目標已存在，未指定 --force 不得覆寫：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".super-eli5-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        _apply_default_mode(temp_name)
        if target.is_symlink():
            raise FileExistsError(f"拒絕寫入 symlink：{target}")
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把 super-eli5 story spec 編譯成零 JavaScript 的單檔 HTML")
    parser.add_argument("spec", help="spec JSON 路徑")
    parser.add_argument("output", help="輸出 HTML 路徑")
    parser.add_argument("--force", action="store_true", help="允許覆寫既有輸出檔")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="輸出必須位於此目錄之內（預設：目前工作目錄）")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出結果")
    args = parser.parse_args(argv)
    configure_stdout()

    report: dict[str, Any] = {"renderer_version": RENDERER_VERSION, "status": "FAIL", "output": args.output}
    try:
        spec = load_spec(args.spec)
    except (OSError, ValueError) as exc:
        report["error"] = f"spec_unreadable: {exc}"
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"FAIL {report['error']}")
        return 1
    validation = validate_spec(spec)
    if not validation.ok:
        report["error"] = "spec_invalid"
        report["validation"] = validation.as_dict()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print("FAIL spec_invalid")
            for item in validation.errors:
                print(f"  ERROR {item.code}: {item.message}")
        return 1
    html_text = render(spec)
    try:
        write_text_atomic(Path(args.output), html_text, force=args.force, workspace=args.workspace)
    except (OSError, PermissionError) as exc:
        report["error"] = f"write_refused: {exc}"
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"FAIL {report['error']}")
        return 1
    report.update(
        {
            "status": "PASS",
            "spec_sha256": spec_sha256(spec),
            "style_sha256": STYLE_SHA256_HEX,
            "html_sha256": hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
            "bytes": len(html_text.encode("utf-8")),
            "warnings": [item.as_dict() for item in validation.warnings],
        }
    )
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"PASS {args.output} spec_sha256={report['spec_sha256']} bytes={report['bytes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
