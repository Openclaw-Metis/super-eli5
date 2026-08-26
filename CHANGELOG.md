# Changelog

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
