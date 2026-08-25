# Readiness Report

本檔是目前 skill 版本的發布證據。每次修改 `SKILL.md`、scripts、references 或 eval assets 後，都必須重新執行機械 gate 並更新本檔。

## 最終 Gate

- 本次審查版本：super-eli5 2026.8.25（validator 1.0.0、renderer 1.0.0、verifier 1.0.0）
- 整體狀態：PASS（create gate PASS、publish gate PASS、security audit PASS）
- 阻擋問題：無
- 稽核日期：2026-08-25
- Git commit：local-only（首次 commit；GitHub 發布擱置中）
- 稽核執行者：local（Linux sandbox，Python 3.12.3；skillops-studio validator 3.1.0，policy 2026.8.7-point-of-use-index-v1）

實際執行的命令與結果（在 repo 根目錄執行，`SKILLOPS` 指向 skillops-studio 的安裝路徑）：

| 命令 | 結果 |
|---|---|
| `python "$SKILLOPS/scripts/stage_gate.py" skills/super-eli5 --stage create --json` | PASS：stage_contract、format、skill_references、unreferenced_files、eval_assets 皆 PASS；capability_chain SKIPPED（非 router）；benchmark SKIPPED |
| `python "$SKILLOPS/scripts/release_gate.py" skills/super-eli5 --stage publish --json` | PASS：上述項目 PASS，skill_security PASS（30 個檔案、0 error、0 warning） |
| `python "$SKILLOPS/modules/skill-evaluation-validation/scripts/format_check.py" skills/super-eli5` | 0 error、0 warning |
| `python "$SKILLOPS/modules/skill-evaluation-validation/scripts/audit_unreferenced_files.py" skills/super-eli5` | 0 個 unreferenced_file、0 個 detached_index_link（2 個索引來源、21 個被引用檔案） |
| `python "$SKILLOPS/modules/skill-evaluation-validation/scripts/audit_skill_references.py" skills/super-eli5` | 0 issues（8 個來源檔） |
| `python -m unittest discover -s tests` | 30 tests OK |
| `python skills/super-eli5/scripts/self_check.py` | PASS：3 個範例；本機來源證據皆 quote-checked，URL 來源為 structural |

未執行或無法執行的項目（誠實記錄，不視為通過）：

- Live trigger eval（`run_eval.py`）需要 `claude` CLI 與模型；本環境沒有，狀態 SKIPPED。eval 案例只做了結構檢查（tags、languages、trigger classes）。
- Frozen live benchmark（`benchmark.json`）不存在，狀態 SKIPPED；本 skill 沒有宣稱取代任何既有 skill，不需要 replacement benchmark。
- 瀏覽器實際檢視 artifact（桌面與 390px）沒有自動化；本次只做了 HTML 標籤平衡、CSP hash、禁用標記與 byte-for-byte 重現檢查，未在真實瀏覽器開啟。

## 格式與結構檢查

- [x] Skill folder 名稱為 kebab-case。
- [x] `SKILL.md` 存在且 YAML frontmatter 有 `name`、`description`、`version`、`license`、`metadata.language: zh-TW`、`metadata.author: Openclaw-Metis`。
- [x] Frontmatter 不含 `<` 或 `>`；description 含觸發語且未超過 1024 字元。
- [x] Skill folder 內沒有 `README.md`（repo 層 README 在 skill folder 外）。
- [x] `role`、`decision_boundary`、`workflow`、`output_contract` 與 `default_follow_through_policy` 都是實質內容。
- [x] 每個 workflow step 都有動作、輸入、輸出與驗證。
- [x] `scripts/` 的四支 Python 皆可 compile，且只用標準函式庫。

## 要求與政策檢查

- [x] Description 清楚說明適用與不適用情境，並列出鄰近 skills 的交棒。
- [x] 人類可讀內容以繁體中文撰寫；程式識別字、schema key、命令與必要術語保留英文。
- [x] Trigger eval 涵蓋 should-trigger、should-not-trigger、near-miss 與 overlap-neighbor；語言涵蓋 zh、en、mixed；trigger class 涵蓋 direct、indirect、negative（14 個案例）。
- [x] Functional eval 涵蓋 happy-path、edge-case 與 failure-mode。
- [x] 外部副作用、核准、rollback 與 lifecycle 規則一致：scripts 不連網、不執行外部程式；寫檔採 no-clobber、workspace 路徑邊界、暫存檔原子替換；覆寫需使用者同意後加 `--force`。
- [x] 安全稽核 PASS：risk signal 只有 `filesystem_write`，且 approval、untrusted boundary、workspace boundary、no-clobber、atomic write、rollback 控制皆被判定有效。

## 常見錯誤檢查

- [x] 沒有遺失的本地 reference。
- [x] `scripts/`、`references/`、`assets/` 沒有未說明的 orphan file；所有連結都是 point-of-use 連結。
- [x] 沒有 placeholder 留在待發布內容（規則文字本身除外）。
- [x] 沒有以人工 checklist 覆蓋機械 gate 的 FAIL／BLOCKED。
- [x] 範例 spec 的 `content_sha256` 由 `--bind` 產生；改動來源檔案會讓 self_check 以 `content_sha256_mismatch` 失敗，這是預期行為。

## 維護

- [x] 已更新版本與稽核日期。
- [x] 已保存 eval 與 regression gates。
- [ ] 需要品質提升宣稱時，已完成可比較的 held-out benchmark（目前沒有此類宣稱，不適用）。
- [ ] 首次在 Windows 11 上執行 `python -m unittest discover -s tests` 與 `python skills/super-eli5/scripts/self_check.py`（本次只在 Linux 驗證；程式碼未使用 POSIX 專屬呼叫，symlink 測試在 Windows 自動略過）。
