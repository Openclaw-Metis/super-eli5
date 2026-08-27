# Changelog

## 2026.8.27

- validator 改採 strict RFC 8259 JSON，拒絕 `NaN`／`Infinity` 與 boolean 冒充 integer。
- reference type contract 強化：edge、trace、module 與 tradeoff 的 id 參照遇到 structured value 時回報精確錯誤，不再拋出 `TypeError`；`options[].nodes` 必須是不可重複的字串陣列。
- 明確執行 `--check-quotes` 或 `--bind` 時，缺失／無法讀取的本機來源改為阻擋錯誤，不再以 structural 警告放行。
- standalone verifier 與 repository release contract 拒絕非標準 JSON；惡意內嵌 spec 會得到 finding 而不是 crash。
- 新增 6 個 failure-mode regression tests；測試增至 39 個。

## 2026.8.26

- 修復跨平台 checkout 換行造成 bundled example hash 在 Windows 失敗。
- standalone verifier 現在無條件由內嵌 spec 與 verification manifest 重建 artifact，正文竄改不再需要 `--spec` 才能偵測。
- renderer 只顯示本次 validator 實際確認的等級；spec 自行宣告的高等級不再具有顯示效力。
- provenance v2：`retrieved_at` 不再視為內容識別；URL 需要內容 SHA-256，Git 身分需要 repo_url 與完整 40 位 commit SHA。
- 新增 p-value 來源快照與回歸測試；測試增至 33 個。

## 2026.8.25

- 初版 super-eli5 skill：六層超白話解說、三層真相（analogy / inferred / verified）、五種 story grammar（concept / module / tradeoff / incident / metric）。
- scripts：validate_spec（結構 + 語意 + provenance 綁定與逐字引述核對）、render_html（零 JavaScript、CSP hash 鎖定、決定性單檔 HTML）、verify_artifact（竄改偵測與配對重現）、self_check。
- 三個 zh-TW 範例（p 值、MAU、儀表板歸零事故）與對應本機來源；schemas/story-spec.v1.schema.json。
- skillops create 與 publish gate PASS，security audit PASS；30 個 unittest。
