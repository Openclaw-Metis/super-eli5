# super-eli5

把複雜的概念、程式或資料模組、方案取捨、事故、指標口徑，講到五歲也能懂，同時誠實標出每句話站在哪一層：只是類比、有理由的推論，還是有來源、有逐字引述、有不可變識別的已驗證事實。需要交付時，再把解說編譯成零 JavaScript、離線可開、可配對驗證的單檔 HTML。

作者：Openclaw-Metis。授權：MIT。主要語言：繁體中文（zh-TW），artifact 另支援 zh-CN 與 en。

## 它跟一般 ELI5 差在哪

| 一般 ELI5 | super-eli5 |
|---|---|
| 把話講簡單 | 六層固定輸出：一句話版 → 一個類比與失真點 → 三層真相 → 一張圖一個場景 → 失效鏡頭與教回來 → 證據表 |
| 類比講完就結束 | 每個類比必須寫「類比在哪裡失真」 |
| 事實與推測混在一起 | analogy / inferred / verified 三層，驗證器擋下「類比當根因」「推論標已驗證」 |
| 「有來源」就算驗證 | verified 需要 locator、逐字 quote、不可變識別；`--bind` 實際讀檔算 SHA-256、核對引述，等級只由檢查結果決定 |
| HTML 是一次性產物 | 同一份 spec 永遠產生相同 bytes；CSP 以樣式 hash 鎖定；內嵌 canonical spec 與 SHA-256；verify 可重現比對 |

五種 story grammar：`concept`、`module`、`tradeoff`、`incident`，以及為資料分析工作加的 `metric`（定義、血緣、口徑、前後比較）。

## 目錄

```text
skills/super-eli5/        Agent Skill 本體（安裝這個資料夾）
  SKILL.md                入口與工作流
  scripts/                validate_spec.py / render_html.py / verify_artifact.py / self_check.py
  references/             三層真相、五種 grammar、spec 契約、寫作規則、QA 清單、readiness report
  assets/examples/        三個 zh-TW 範例 spec 與它們引用的本機來源
  assets/templates/       spec 起手骨架
  assets/evals/           trigger / functional eval 案例與 regression gates
  schemas/                story-spec.v1.schema.json（結構層）
  agents/openai.yaml      Codex 顯示中繼資料
tests/                    unittest、跨平台 release contract 與 module / tradeoff / en fixtures
docs/design-research/     設計依據：Fireworks Open ELI5 深度研究與程式碼審查報告
```

## 安裝

需求：Python 3.9 以上；scripts 只用標準函式庫，不連網、不安裝套件。

用 Agent Skills CLI（版本固定，避免 `@latest` 漂移；`OWNER` 換成 repo 所在帳號）：

```bash
npx skills@1.5.23 add OWNER/super-eli5 -g -a codex -a claude-code -y
```

或手動複製 `skills/super-eli5` 到 host 的 skills 目錄（例如 Claude Code 的 `~/.claude/skills/super-eli5`、Codex 的 `~/.codex/skills/super-eli5`）。安裝後先跑：

```bash
python skills/super-eli5/scripts/self_check.py
```

## 快速上手

在 skill 目錄內，以內建的 MAU 範例走完整流程：

```bash
cd skills/super-eli5

# 1. 結構與語意驗證，並對本機來源做 SHA-256 綁定與逐字引述核對
python scripts/validate_spec.py assets/examples/metric-mau.zh-TW.json \
  --source-root assets/examples/sources --check-quotes --json

# 2. 編譯成零 JavaScript 的單檔 HTML；可見檢驗等級只採用本次來源檢查結果
python scripts/render_html.py assets/examples/metric-mau.zh-TW.json out/mau.html \
  --workspace out --source-root assets/examples/sources --check-quotes

# 3. 配對驗證：spec hash、CSP hash、禁用標記、byte-for-byte 重現
python scripts/verify_artifact.py out/mau.html --spec assets/examples/metric-mau.zh-TW.json --json
```

自己的解說：先照 `references/` 的規則寫 `spec.json`，用 `--bind --out spec.bound.json` 寫入來源 hash 與檢驗等級，再 render 與 verify。完整工作流、輸出契約與交付訊息模板在 `skills/super-eli5/SKILL.md`。

## 安全模型

- 驗證器平時只讀；`--bind` 只寫到明確指定的 `--out`，並採 no-clobber、拒絕 symlink、暫存檔加原子替換。renderer 另要求輸出位於 `--workspace` 路徑邊界內；兩者要覆寫既有檔案都必須明確加 `--force`。
- spec 與 artifact 內嵌 manifest 採 strict RFC 8259 JSON；`NaN`／`Infinity`、boolean 冒充 integer、非字串 reference 都會被拒絕，惡意輸入會回報 FAIL 而不是讓 verifier crash。
- locator 只接受 http(s) URL 或相對 POSIX 路徑；絕對路徑、`..`、`~`、`javascript:`、`data:` 一律拒絕，來源讀取不會逃出 `--source-root`。
- artifact 不含任何 script、外部資源、inline style 屬性或事件屬性；CSP 為 `default-src 'none'; style-src 'sha256-…'`；只有 evidence 宣告過的 URL 會成為連結。
- renderer 不採信 spec 自稱的檢驗等級；可見等級取自本次 validator 結果，存入獨立、雜湊鎖定的 verification manifest。verifier 即使未提供 `--spec`，也會重建整份 HTML 比對 bytes。
- URL 的 `retrieved_at` 只記錄時間，不能識別內容；verified URL 另需 `content_sha256`，Git 證據則需 `repo_url` 與完整 40 位 `commit_sha`。
- 來源內容一律視為不可信資料：log、筆記、文件裡的句子只證明「有人這樣寫」；「已驗證」代表可追溯與可重現，不代表來源本身正確。產物定位是給人審閱的衍生解說，不是權威紀錄。

## 開發與驗證

```bash
python -m unittest discover -s tests -v          # 39 個測試：契約、strict JSON、provenance、綁定、對抗文字、決定性、竄改、檔案安全
python skills/super-eli5/scripts/self_check.py   # 內建範例 validate → render ×2 → verify
python tests/release_contract.py --json          # CI 可重跑的結構、eval、reference、lifecycle 與 LF 發版契約
```

Skill 本身以 skillops 相容的 revise 與 publish gate 驗證，結果記錄在 `skills/super-eli5/references/readiness_report.md`。CI 在 Ubuntu 與 Windows 上執行 repository-local release contract、compile、unittest 與 self-check，Actions 以完整 commit SHA 釘住。

## 設計依據與致謝

設計依據是 `docs/design-research/` 內的研究報告：它把 Fireworks Open ELI5 的三層真相、story grammar、failure lens、trace playback、teach-back 與 deterministic artifact 視為核心價值，並指出「verified 只是結構驗證」「缺 provenance」「缺 zh-TW fixture」等缺口；本 skill 直接補上這些缺口。

本 skill 是獨立實作，靈感來自 Anthropic community `eli5` skill 與 Fireworks Open ELI5（Apache-2.0）的證據契約構想，未使用其程式碼；與兩者皆無隸屬或背書關係。
