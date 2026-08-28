# Readiness Report

本檔只記錄目前版本實際執行過的發布證據；人工判斷不能覆蓋機械 gate 的 FAIL 或 BLOCKED。

## Final Gate

- Skill version: 2026.8.28
- Components: validator 1.3.0、renderer 1.1.0、verifier 1.4.0
- Overall status: PASS（本地 revise stage、security stage、publish preflight、repository release contract、compile、41 tests 與 self-check；不含 frozen live benchmark、遠端 CI 或實際發布）
- Blocking issues: none for local release readiness；本輪遠端 push／Release 已由使用者授權，實際狀態以 GitHub commit、Actions 與 Release 紀錄為準
- Audit date: 2026-08-28
- Git baseline: `6590ed0bacf0c4cc69555a10e7be4db1e4065a6c`；candidate 為本版 release commit，精確 SHA 以 GitHub 紀錄為準，rollback 為回復 baseline commit
- Auditor environment: Linux sandbox、Python 3.12.3

## Executed Evidence

以下命令均在 repository root 實際執行：

| Command | Result |
|---|---|
| `python $SKILLOPS/scripts/stage_gate.py skills/super-eli5 --stage revise --json` | PASS（同步 readiness 後第二次）：format、references、orphan、consistency、eval 與 instruction-control 全部 PASS；benchmark SKIPPED |
| `python $SKILLOPS/scripts/stage_gate.py skills/super-eli5 --stage security --json` | PASS：36 files／388,033 bytes；0 errors、0 warnings、0 suppressed，analysis complete |
| `python $SKILLOPS/scripts/release_gate.py skills/super-eli5 --stage publish --json` | PASS：evaluation、security、lifecycle 與 publish audits 全部 PASS；security 重掃 36 files／388,242 bytes，benchmark SKIPPED |
| `python tests/release_contract.py --json` | PASS（同步 readiness 後第二次）：8 個 JSON、8 個 workflow steps、12 個 Markdown；0 findings |
| `python -m py_compile skills/super-eli5/scripts/*.py` | PASS |
| `python -m unittest discover -s tests -v` | PASS：41 tests |
| `python skills/super-eli5/scripts/self_check.py --json` | PASS：3 個 zh-TW 範例；5 筆本機 verified evidence 全部 quote-checked |

`$SKILLOPS` 指向權威 `origin/master@c792c36db0aa598fe17551e22f911c6288772802` 的 `skillops-studio`。GitHub Actions 會在每個 push 上，於 Ubuntu 與 Windows 重跑 repository-local release contract、compile、41 tests 與 self-check；遠端狀態以 release commit 的 Actions 紀錄判定，本檔不預先宣稱通過。

## Optimization Decision

- Decision: ACCEPT（E2 deterministic revise）；模型品質最佳化 claim 降級為 BENCHMARK_DESIGN
- Target skill: `skills/super-eli5`
- Baseline: version 2026.8.27, commit `6590ed0`, 39 tests PASS；GitHub Actions run 33077093243 為 success
- Candidate: version 2026.8.28 release commit；精確 SHA 以 GitHub 紀錄為準
- Objective: 在不改 story spec v1 與 deterministic HTML bytes 的前提下，消除 duplicate-key parser ambiguity、無效 UTF-8 quote false match，以及新版 SkillOps orphan findings
- Edit-generation split: 2 個由 adversarial code audit 產生的 regression cases；baseline 會接受 duplicate object keys，也可能用 Unicode replacement character 把無效 UTF-8 來源升成 quote-checked
- Held-out validation: 原有 39 tests 與 3 個 bundled examples；candidate 全部 PASS，三個既有 HTML artifact hash 未改變
- Final test: repository release contract、SkillOps revise、security stage 與 publish preflight 均 PASS；frozen model benchmark SKIPPED
- ROI: candidate 41 tests 牆鐘時間 0.134 秒，低於 30 秒 regression budget；尚無 paired baseline timing，不宣稱速度提升
- Trigger / overlap: description、primary job、negative triggers 與 14 筆 trigger/functional eval 的意圖邊界未擴張；instruction-control findings 由 10 降為 0
- Accepted edits: point-of-use resource wiring、duplicate-key rejection、strict UTF-8 quote check、repository-local JSON audit、2 個 adversarial regressions
- Rejected edits: 未改 story spec version、未重寫 renderer、未擴張 skill primary job
- Rollback path: 回退至 baseline commit `6590ed0`
- Residual risk: 未執行 frozen-model/live trigger benchmark，不宣稱模型輸出品質、ROI 或跨 host performance 提升

## Common Errors and Remediation Evidence

本版的第一次 revise stage gate 因 readiness report 仍指向 2026.8.27 而 FAIL；未跳過 gate。第一次 repository release contract 也因同一 stale version finding 而 FAIL。同步版本、audit date 與實際命令後，兩者第二次重跑均 PASS；security stage 也已 PASS。

1. point-of-use／orphan：第一次最新版 gate 有 12 個 unreferenced files 與 2 個 detached links；把 starter fixtures、policies、schema、scripts、QA 與 lifecycle 連回首次使用步驟後，重跑該 audit 為 PASS、0 findings。
2. instruction control：為讀檔、verified 分級、寫入、placeholder 與 provenance 補上可觀察條件、正向替代行動與停止路徑；advisory findings 由 10 降為 0。
3. JSON common error：validator、verifier 共用的 strict loader 與 repository release contract 現在拒絕任何層級的 duplicate object key，避免 first-wins／last-wins 歧義。
4. provenance common error：明確 `--check-quotes` 或 `--bind` 時以 strict UTF-8 解碼來源；無效 bytes 回報 `source_not_utf8`，保留實際 content-bound 等級但不升為 quote-checked。

## Structure, Eval, and Security-Relevant Checks

- SKILL.md 的 role、decision boundary、8-step workflow、output contract、follow-through policy 與 worked examples 均通過機械 parser。
- Trigger eval 共有 direct 7、indirect 2、negative 5；涵蓋 zh、en、mixed，以及 should-trigger、should-not-trigger、near-miss、overlap-neighbor。
- Functional eval 涵蓋 happy-path、edge-case、failure-mode；沒有弱到無法驗證的 expectation。
- 最新 point-of-use reference 與 unreferenced-file audits 均 PASS；30 個 accepted Markdown links、0 ignored links、0 findings。
- Artifact regression 覆蓋：hostile text escaping、CSP/style hash、禁止標記、非法 link、standalone 正文竄改、非標準與 duplicate-key JSON、spec／manifest hash、byte reproduction。
- Filesystem regression 覆蓋：workspace boundary、no-clobber、symlink rejection、atomic write、來源 root escape、missing source 與 invalid UTF-8 quote-check failure。

## Limitations

- Live trigger eval 與 frozen model benchmark 未執行；本版維持 BENCHMARK_DESIGN，不宣稱模型輸出品質、ROI 或跨 host performance 提升。
- 遠端 push、GitHub Actions 與 Release 不算本地 gate 證據；只在 release commit 的 CI 成功後建立 Release，遠端失敗時停止並保留 tag／rollback 狀態供追查。
- 真實瀏覽器的桌面與 390px 視覺檢查未自動化；HTML 安全與結構由 verifier 測試，視覺品質仍需人工抽查。
- URL 內容不由 scripts 連網重抓，因此工具最多給 URL evidence `structural`；`content_sha256` 與 `retrieved_at` 仍需取證者對實際讀取 bytes 負責。
