# Changelog

## 2026.8.25

- 初版 super-eli5 skill：六層超白話解說、三層真相（analogy / inferred / verified）、五種 story grammar（concept / module / tradeoff / incident / metric）。
- scripts：validate_spec（結構 + 語意 + provenance 綁定與逐字引述核對）、render_html（零 JavaScript、CSP hash 鎖定、決定性單檔 HTML）、verify_artifact（竄改偵測與配對重現）、self_check。
- 三個 zh-TW 範例（p 值、MAU、儀表板歸零事故）與對應本機來源；schemas/story-spec.v1.schema.json。
- skillops create 與 publish gate PASS，security audit PASS；30 個 unittest。
