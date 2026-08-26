# Story spec v1 契約

這份契約是 `scripts/validate_spec.py` 實際執行的規則；文件與程式不一致時以程式為準，並回頭修文件。機器可讀版本在 [story-spec.v1.schema.json](../schemas/story-spec.v1.schema.json)，它只表達結構，語意規則（mode 契約、三層真相）仍由驗證器負責。

## 頂層欄位

| 欄位 | 必填 | 規則 |
|---|---|---|
| `version` | 是 | 固定為 `1` |
| `language` | 是 | `zh-TW`、`zh-CN`、`en`；決定 artifact 的 UI 文字與 `lang` 屬性 |
| `mode` | 是 | `concept`、`module`、`tradeoff`、`incident`、`metric` |
| `title` | 是 | 最多 80 個全形字寬 |
| `audience` | 是 | 最多 40；寫具體的人，例如「第一次看月報的行銷主管」 |
| `one_liner` | 是 | 一句話、不可換行、最多 60；五歲版 |
| `analogy` | 是 | `text`（最多 300）與 `limits`（最多 300）都必填 |
| `ladder` | 是 | `analogy`、`truth`、`caveat` 三層各最多 400 |
| `scenes` | 是 | 1 至 7 個場景 |
| `trace` | 否 | 0 至 24 步 |
| `failure_lens` | 是 | 1 至 8 個失效鏡頭 |
| `teach_back` | 是 | 1 至 3 個教回來問題 |
| `glossary` | 否 | 0 至 16 個詞彙 |
| `evidence` | 是 | 1 至 40 筆 |
| `mode_data` | 是 | 依 mode 的契約 |

沒有列出的頂層欄位一律拒絕（closed schema）。長度以「全形字寬」計：中文一字算 2，英數算 1，所以英文可以寫到兩倍字元數。

## 場景、節點、連線

- `scenes[]`：`id`、`title`（60）、`caption`（200）、`nodes`（2 至 6）、`edges`（0 至 12）。
- `nodes[]`：`id`、`label`（30；SVG 會自動換行到 3 行）、`status`、可選 `note`（160）、`evidence`（evidence id 陣列）。
- `edges[]`：`from`、`to` 必須是同一場景的 node id；不可自我連結、不可重複；可選 `label`（30）。
- node id 在整份 spec 內全域唯一，trace 才能用 `scene` + `node` 精準指到節點。
- `verified` 節點至少引用一筆 `verified` evidence；引用不存在的 evidence id 直接失敗。

## ID 與文字規則

- 所有 id 符合 `^[a-z][a-z0-9_-]{0,31}$`，同類別內唯一（scene、node、failure_lens、evidence、option 各自一組）。
- 文字不可含控制字元（換行與 tab 除外）；HTML renderer 會對所有文字做 escape，所以 `<script>` 之類的字串只會被當成文字顯示。

## trace

- `step` 從 1 開始連續編號；`scene` 必須是 `node` 所屬的場景。
- artifact 以純 CSS 提供逐步回放（radio 按鈕），最多 24 步。

## failure_lens、teach_back、glossary

- `failure_lens[]`：`id`、`what_breaks`（120）、`symptom`（200）、可選 `status`（預設 inferred，不可 analogy）、`evidence`。
- `teach_back[]`：`question`（160）、`answer`（300）。答案在 artifact 內預設收合。
- `glossary[]`：`term`（40）、`plain`（160）；詞彙不可重複。

## evidence

| 欄位 | 規則 |
|---|---|
| `id` | 必填 |
| `status` | `analogy` / `inferred` / `verified` |
| `claim` | 必填，最多 300 |
| `locator` | verified 必填；http(s) URL 或相對 POSIX 路徑 |
| `quote` | verified 必填，最多 240，逐字 |
| `retrieved_at` | ISO 8601；URL 來源的 verified 必填 |
| `repo_url` | http(s) repository URL；與 `commit_sha` 成對出現 |
| `commit_sha` | 完整 40 位小寫十六進位 Git commit SHA；與 `repo_url` 成對出現 |
| `content_sha256` | 來源 bytes 的 64 位小寫十六進位 SHA-256；本機來源由 `--bind` 自動填；verified URL 必填（除非已有 repo_url + commit_sha） |
| `line_start` / `line_end` | 成對出現，`1 <= start <= end`；quote 必須落在範圍內 |
| `reasoning` | inferred 必填，最多 300 |
| `note` | 可選，最多 200 |
| `verification` | 只有 verified 可有；`structural` / `content-bound` / `quote-checked`，由 `--bind` 寫入 |

## mode_data 契約摘要

- `concept`：`misconceptions[]`（1 至 8；`myth`、`reality`）。
- `module`：`source_root`、`entry`、`exit`、`inputs[]`、`outputs[]`；至少一筆 verified 本機路徑 evidence。
- `tradeoff`：`options[]`（2 至 5；`id`、`name`、`gains[]`、`costs[]`、可選 `nodes[]`）、`decision_rule`、`recommendation{option,status,because,evidence}`。
- `incident`：`timeline[]`（2 至 24；`t`、`event`、`kind`、`evidence`）、`root_cause{text,status,evidence}`、可選 `contributing_factors[]`。
- `metric`：`metric_name`、`definition{text,status,evidence}`、`lineage[]`（1 至 12；`from`、`to`、`transform`）、`scope{grain,time_window,filters}`、可選 `comparison{before,after,evidence}`。

完整語意見 [story grammars](story-grammars.md)；證據規則見 [truth ladder](truth-ladder.md)。

## HTML artifact 契約

`scripts/render_html.py` 的輸出必須同時滿足下列條件，`scripts/verify_artifact.py` 會逐項檢查：

1. 只有一個 `<style>` 區塊；其 SHA-256 同時等於 `meta[name=super-eli5-style-sha256]`、CSP `style-src 'sha256-…'` 與 renderer 內建樣式。
2. CSP 固定為 `default-src 'none'; style-src 'sha256-…'; base-uri 'none'; form-action 'none'`；沒有 script-src，代表任何 script 都被瀏覽器拒絕。
3. 不含 script、iframe、object、embed、form、link、base、img、video、audio、inline `style=` 屬性、`on*` 事件屬性、`javascript:`、meta refresh、`src=`；CSS 內不含 `@import` 或外部 `url()`。
4. 所有 `href` 只能是頁內錨點，或內嵌 spec 的 evidence 內宣告過的 http(s) locator（帶 `rel="noopener noreferrer"`）。
5. `pre#super-eli5-spec` 內嵌 HTML-escaped 的 canonical spec；`meta[name=super-eli5-spec-sha256]` 等於 canonical JSON（`sort_keys`、緊湊分隔、UTF-8）的 SHA-256。
6. `pre#super-eli5-verification` 內嵌本次工具產生的 evidence→level manifest；其 canonical hash 寫在 `meta[name=super-eli5-verification-sha256]`。renderer 不採信 spec 自行宣告的等級。
7. 同一份 spec 與 verification manifest 重新 render 必須 byte-for-byte 相同；verifier 不需外部 `--spec` 就會重建比對，提供 `--spec` 時再額外確認配對。
8. 輸出沒有時間戳、隨機值或環境資訊。
