# Readiness Report

本檔只記錄目前版本實際執行過的發布證據；人工判斷不能覆蓋機械 gate 的 FAIL 或 BLOCKED。

## Final Gate

- Release version: super-eli5 2026.8.27
- Components: validator 1.2.0、renderer 1.1.0、verifier 1.3.0
- Overall status: PASS（local revise gate、publish gate、repository release contract 與功能回歸全部 PASS）
- Blocking issues: none
- Audit date: 2026-08-27
- Git commit: release commit on `main`；精確 SHA 與遠端 CI 結果以 GitHub commit／Actions 紀錄為準，避免在 commit 內容內建立自我參照
- Auditor environment: Linux sandbox、Python 3.12.3

## Executed Evidence

以下命令均在 repository root 實際執行：

| Command | Result |
|---|---|
| `python $SKILL_CREATOR/scripts/stage_gate.py skills/super-eli5 --stage revise --json` | PASS：format、structure、workflow contract、semantics、gate language、lifecycle、eval coverage／quality、golden trigger set、migration governance、references、healthcheck 全部 PASS；benchmark SKIPPED |
| `python $SKILL_CREATOR/scripts/release_gate.py skills/super-eli5 --stage publish --json` | PASS：publish audits 全部 PASS；benchmark SKIPPED |
| `python tests/release_contract.py --json` | PASS：8 個 JSON、8 個 workflow steps、12 個 Markdown；0 findings |
| `python -m py_compile skills/super-eli5/scripts/*.py` | PASS |
| `python -m unittest discover -s tests -v` | PASS：39 tests |
| `python skills/super-eli5/scripts/self_check.py --json` | PASS：3 個 zh-TW 範例；5 筆本機 verified evidence 全部 quote-checked |

`$SKILL_CREATOR` 指向本次環境中的 `skill-creator-advanced` 安裝目錄。GitHub Actions 會在每個 release commit 上，於 Ubuntu 與 Windows 重跑 repository-local release contract、compile、39 tests 與 self-check；遠端狀態應以該 commit 的 Actions 紀錄判定，本檔不預先宣稱它通過。

## Optimization Decision

- Decision: ACCEPT
- Target skill: `skills/super-eli5`
- Baseline: version 2026.8.26, commit `cf9af7a`, 33 tests PASS
- Candidate: version 2026.8.27
- Objective: 在不改 story spec v1 與 deterministic HTML bytes 的前提下，讓 malformed JSON、reference type confusion 與明確 provenance check 不會誤放行或 crash
- Edit-generation split: 6 個由 code audit 產生的 synthetic adversarial regression cases；baseline 呈現 false PASS、非標準 JSON 接受或未處理例外
- Held-out validation: 原有 33 個 tests 與 3 個 bundled examples；candidate 全部 PASS，既有 artifact hash 未改變
- Final test: repository release contract、SkillOps revise stage gate 與 publish release gate 全部 PASS；benchmark SKIPPED
- ROI: unittest 牆鐘時間由 baseline 0.067 秒到 candidate 0.079 秒，增加 0.012 秒，低於 30 秒 gate；token 指標不適用於本機 deterministic scripts
- Trigger / overlap: description、primary job、negative triggers 與 14 筆 trigger/functional eval 均未改，neighbor confusion surface 不變
- Accepted edits: strict JSON loader、integer/type contract、reference array contract、explicit quote-check/bind source gate、verifier malformed-input findings
- Rejected edits: 未改 story spec version、未重寫 renderer、未擴張 skill primary job
- Rollback path: 回退至 baseline commit `cf9af7a`
- Residual risk: 未執行 frozen-model/live trigger benchmark，不宣稱模型輸出品質、ROI 或跨 host performance 提升

## Remediation Evidence

本版的第一次 revise stage gate 因 readiness report 仍指向 2026.8.26 而 FAIL；未跳過 gate。同步版本、audit date 與實際命令後重跑，revise 與 publish gate 均 PASS。其餘已關閉的缺口：

1. strict RFC 8259 JSON：拒絕 `NaN`、`Infinity`、`-Infinity` 與過深巢狀；release contract 與 verifier 使用同一邊界。
2. scalar/reference type confusion：boolean 不可冒充 version／trace integer；edge、trace、module、tradeoff reference 先驗型別再查表，不再拋 `TypeError`。
3. `tradeoff.options[].nodes` 現在必須是不可重複的 node id 字串陣列，validator、schema 與文件一致。
4. 明確使用 `--check-quotes` 或 `--bind` 時，來源不存在或不可讀會阻擋，不再以 structural 警告放行。
5. standalone verifier 遇到非標準內嵌 JSON 會回報 `embedded_spec_invalid_json`，不再於 canonicalization crash。

## Structure, Eval, and Security-Relevant Checks

- SKILL.md 的 role、decision boundary、8-step workflow、output contract、follow-through policy 與 worked examples 均通過機械 parser。
- Trigger eval 共有 direct 7、indirect 2、negative 5；涵蓋 zh、en、mixed，以及 should-trigger、should-not-trigger、near-miss、overlap-neighbor。
- Functional eval 涵蓋 happy-path、edge-case、failure-mode；沒有弱到無法驗證的 expectation。
- Local reference 與 unreferenced-file audits 均 PASS；migration governance 六個必要章節齊全。
- Artifact regression 覆蓋：hostile text escaping、CSP/style hash、禁止標記、非法 link、standalone 正文竄改、非標準內嵌 JSON、spec／manifest hash、byte reproduction。
- Filesystem regression 覆蓋：workspace boundary、no-clobber、symlink rejection、atomic write、來源 root escape，以及 explicit quote check／bind 的 missing-source failure。

## Limitations

- Live trigger eval 與 frozen model benchmark 未執行；publish gate 將 benchmark 標為 SKIPPED。這不阻擋本次發布，但本版不宣稱 ROI、模型輸出品質提升幅度或跨 host performance。
- 真實瀏覽器的桌面與 390px 視覺檢查未自動化；HTML 安全與結構由 verifier 測試，視覺品質仍需人工抽查。
- URL 內容不由 scripts 連網重抓，因此工具最多給 URL evidence `structural`；`content_sha256` 與 `retrieved_at` 仍需取證者對實際讀取 bytes 負責。
