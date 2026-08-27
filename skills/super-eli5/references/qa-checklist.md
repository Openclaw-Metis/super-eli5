# 交付前 QA

分兩段：機械檢查先跑，任何一項 FAIL 就不交付；人工檢查只在機械檢查全部 PASS 之後做，且不能用人工判斷取代機械 FAIL。

## 機械檢查（依序執行）

| 步驟 | 命令 | 通過條件 |
|---|---|---|
| 1. 結構與語意 | `python scripts/validate_spec.py spec.json --json` | `status` 為 `PASS` |
| 2. 綁定本機證據 | `python scripts/validate_spec.py spec.json --source-root SRC --check-quotes --bind --out spec.bound.json` | 每筆本機 verified 顯示 `quote-checked` |
| 3. 編譯 HTML | `python scripts/render_html.py spec.bound.json out/explainer.html --workspace out --source-root SRC --check-quotes` | 印出 `PASS`、`spec_sha256` 與本次 verification mapping |
| 4. 配對驗證 | `python scripts/verify_artifact.py out/explainer.html --spec spec.bound.json --json` | `reproduction.byte_identical` 與 `pair.byte_identical` 都為 `true`，`findings` 為空 |
| 5. 環境健康 | `python scripts/self_check.py` | 三個內建範例全部 PASS |

- `SRC` 是來源根目錄（例如 repo 根或 `assets/examples/sources`）；locator 一律相對於它。
- 步驟 2 的輸出檔已存在時要明確加 `--force`；不要用 `--force` 蓋掉還沒看過的檔案。
- 步驟 3 的輸出必須在 `--workspace` 之內；預設是目前工作目錄。
- URL 來源需要 retrieved_at 與內容 hash，且只能到 `structural`；交付訊息要說明它們未經工具比對。

## 人工檢查

- 類比：用類比推出來的結論，在技術事實層是否仍然成立？`analogy.limits` 是否指出真正會誤導的地方？
- 一句話版：不看其他內容，五歲小孩或只讀第一行的主管能複述嗎？有沒有偷渡術語？
- 三層真相：`caveat` 是真的會被誤用的地方，還是形式上的免責？
- verified：每一筆都是實際打開來源後寫的嗎？quote 是逐字嗎？URL 有 `retrieved_at` 與內容 hash 嗎？Git 證據有 repo_url 與完整 commit SHA 嗎？
- inferred：解說文字裡聽得出這是推論嗎？根因或建議是推論時有沒有明說？
- 失效鏡頭：症狀是讀者真的會看到的畫面，還是內部術語？
- 教回來：問題能只靠這份解說回答嗎？答案有沒有引入解說裡沒講的新概念？
- 隱私：locator、quote、title 是否含使用者名稱、絕對路徑、內部主機名、機密數字？
- 語言：解說語言與使用者一致；zh-TW 用語符合台灣慣例。
- HTML：用瀏覽器打開 artifact，桌面與 390px 寬度各看一次：場景圖沒有被裁切、trace 按鈕可切換、教回來可展開、證據表可捲動。這一步沒有自動化，不能宣稱已做。

## 交付訊息模板

```text
已完成 super-eli5 解說：{title}（{mode}，對象：{audience}）
- artifact：{路徑}（{bytes} bytes，零 JavaScript，離線可開）
- spec SHA-256：{hash}
- 證據：verified {n}（quote-checked {k}、structural {m}）、inferred {i}、analogy {a}
- 未經工具比對的來源：{URL 清單或「無」}
- 仍是推論的關鍵判斷：{根因 / 建議 / 定義，或「無」}
- 建議下一步：{請領域專家審閱來源 / 補 content_sha256 / 補 repo_url 與完整 commit_sha}
```

## 常見 FAIL 與修法

| 錯誤碼 | 原因 | 修法 |
|---|---|---|
| `verified_quote_missing` | verified 沒有 quote | 打開來源，抄一段逐字短引述 |
| `verified_immutable_ref_missing` | 沒有內容 hash，或沒有完整 Git 身分 | 本機檔案用 `--bind`；URL 補來源 bytes hash；Git 補 repo_url 與完整 commit_sha |
| `verified_url_content_identity_missing` | URL 只有讀取時間，沒有內容識別 | 補 content_sha256，或可驗證的 repo_url + 完整 commit_sha |
| `git_identity_incomplete` | commit_sha 與 repo_url 只出現一個 | 補成成對欄位；commit_sha 必須完整 40 位 |
| `quote_not_found` | 引述不在來源或行號範圍內 | 重新核對來源；改行號或改引述；仍找不到就降為 inferred |
| `content_sha256_mismatch` | 來源已改動 | 重新讀來源、更新解說、重新 `--bind` |
| `source_not_found` | 明確要求 quote check／bind，但 locator 在來源根目錄下不存在 | 修正 `--source-root` 或 locator；真的讀到來源後再執行，不可降成 structural 放行 |
| `status_analogy_forbidden` | 類比被當成根因、定義或建議 | 改成 inferred 並補 reasoning，或找來源升級為 verified |
| `analogy_only` | 所有節點都是類比 | 至少加一個技術事實節點 |
| `timeline_recovery_before_break` | 恢復事件早於第一次出錯 | 檢查時間與 kind |
| `comparison_evidence_missing` | 前後比較沒有證據 | 兩邊的數字都要有來源 |
| `module_local_evidence_missing` | module 模式沒有本機 verified 來源 | 真的讀程式再寫；讀不到就改 concept |
| `write_refused` | 輸出已存在、是 symlink 或逃出 workspace | 換路徑；確定要覆寫才加 `--force` |
