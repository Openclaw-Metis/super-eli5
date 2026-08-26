# Readiness Report

本檔只記錄目前版本實際執行過的發布證據；人工判斷不能覆蓋機械 gate 的 FAIL 或 BLOCKED。

## Final Gate

- Release version: super-eli5 2026.8.26
- Components: validator 1.1.0、renderer 1.1.0、verifier 1.2.0
- Overall status: PASS（local revise gate、publish gate、repository release contract 與功能回歸全部 PASS）
- Blocking issues: none
- Audit date: 2026-08-26
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
| `python -m unittest discover -s tests -v` | PASS：33 tests |
| `python skills/super-eli5/scripts/self_check.py --json` | PASS：3 個 zh-TW 範例；5 筆本機 verified evidence 全部 quote-checked |

`$SKILL_CREATOR` 指向本次環境中的 `skill-creator-advanced` 安裝目錄。GitHub Actions 會在每個 release commit 上，於 Ubuntu 與 Windows 重跑 repository-local release contract、compile、33 tests 與 self-check；遠端狀態應以該 commit 的 Actions 紀錄判定，本檔不預先宣稱它通過。

## Remediation Evidence

本版關閉前次審查的五個阻擋面：

1. 新增 root `.gitattributes`：`* text=auto eol=lf`，避免 Windows checkout 將 bundled source bytes 改成 CRLF。
2. verifier 無條件使用內嵌 spec 與 verification manifest 重建 artifact；沒有 `--spec` 時仍會偵測正文竄改。
3. renderer 不採信 spec 自稱的 verification；可見等級只來自本次 validator，並以獨立 manifest hash 鎖定。
4. readiness evidence 改為本版實際命令；CI 新增 `tests/release_contract.py`，不再只有 compile／unittest／self-check。
5. provenance v2：`retrieved_at` 只代表讀取時間；verified URL 需要 content SHA-256，Git 身分需要 `repo_url` 與完整 40 位 `commit_sha`。

## Structure, Eval, and Security-Relevant Checks

- SKILL.md 的 role、decision boundary、8-step workflow、output contract、follow-through policy 與 worked examples 均通過機械 parser。
- Trigger eval 共有 direct 7、indirect 2、negative 5；涵蓋 zh、en、mixed，以及 should-trigger、should-not-trigger、near-miss、overlap-neighbor。
- Functional eval 涵蓋 happy-path、edge-case、failure-mode；沒有弱到無法驗證的 expectation。
- Local reference 與 unreferenced-file audits 均 PASS；migration governance 六個必要章節齊全。
- Artifact regression 覆蓋：hostile text escaping、CSP/style hash、禁止標記、非法 link、standalone 正文竄改、spec／manifest hash、byte reproduction。
- Filesystem regression 覆蓋：workspace boundary、no-clobber、symlink rejection、atomic write 與來源 root escape。

## Limitations

- Live trigger eval 與 frozen model benchmark 未執行；publish gate 將 benchmark 標為 SKIPPED。這不阻擋本次發布，但本版不宣稱 ROI、模型輸出品質提升幅度或跨 host performance。
- 真實瀏覽器的桌面與 390px 視覺檢查未自動化；HTML 安全與結構由 verifier 測試，視覺品質仍需人工抽查。
- URL 內容不由 scripts 連網重抓，因此工具最多給 URL evidence `structural`；`content_sha256` 與 `retrieved_at` 仍需取證者對實際讀取 bytes 負責。
