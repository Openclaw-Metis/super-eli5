# 五種 story grammar

每份 super-eli5 解說只選一種 grammar；grammar 決定場景該怎麼排、哪些節點不能少、`mode_data` 要放什麼。選錯 grammar 時，驗證器通常會用 mode 契約錯誤告訴你。

| grammar | 回答的問題 | 典型輸入 | 場景建議 |
|---|---|---|---|
| `concept` | 這是什麼、為什麼這樣運作 | 名詞、原理、統計概念 | 1 至 3 個場景：正常情況、常見誤解、邊界 |
| `module` | 這段程式 / 查詢 / pipeline 在做什麼 | 真的讀過的檔案 | 1 至 3 個場景：入口到出口、關鍵分支、失敗路徑 |
| `tradeoff` | A 和 B 該選哪個、為什麼 | 兩個以上方案 | 1 至 2 個場景：方案並排、決策規則 |
| `incident` | 為什麼壞掉、怎麼恢復 | log、告警、事後筆記 | 2 至 3 個場景：正常流程、斷點、恢復 |
| `metric` | 這個數字是什麼、怎麼算、為什麼變 | SQL、指標字典、報表 | 1 至 3 個場景：計算流程、口徑變更、比較 |

## concept

- 必要：`mode_data.misconceptions`（1 至 8 組 `myth` / `reality`）。誤解是概念解說最有價值的部分，寫使用者真的會講出來的句子。
- 節點：至少一個 `inferred` 或 `verified` 的技術事實節點；示範數字用 `analogy` 標明是虛構。
- 資料分析範例：p 值、信賴區間、留存率的分母、同期比較的季節性。

## module

- 必要：`source_root`（相對路徑）、`entry` 與 `exit`（存在且非類比的 node id）、`inputs`、`outputs`。
- 至少一筆 `verified` evidence 指向本機相對路徑：module 解說的前提是「真的讀過程式」。只有 URL 時不要用 module，改用 concept 並把程式行為標為 inferred。
- 讀不到的相鄰模組（例如 `write_table` 定義在別處）標成 `inferred`，並在 reasoning 寫「本次沒有讀」。
- 資料分析範例：dbt model、每日聚合 script、notebook 的資料清理段落、報表的 SQL。

## tradeoff

- 必要：`options`（2 至 5 個，各自 `gains` 與 `costs` 至少一項）、`decision_rule`（可以用一句話判斷的規則）、`recommendation`（`option` 必須是 options 內的 id，`status` 不可為 analogy）。
- 建議是 `verified` 時，必須引用記錄那個決策的來源（例如 ADR）；沒有來源就誠實標 `inferred`。
- 不要把「贏家」寫進 truth 層；truth 層寫的是兩邊各付出什麼、得到什麼。
- 資料分析範例：批次 vs 串流、抽樣 vs 全量、寬表 vs 星型、用 median 還是 mean。

## incident

- 必要：`timeline`（2 至 24 個事件，ISO 8601 時間由早到晚、時區一致）、`root_cause`（`status` 為 inferred 或 verified）、可選 `contributing_factors`。
- 時間軸恰好一個 `first_break`，且 `first_break` 之後至少一個 `recovery`；`detection` 與 `mitigation` 幫讀者看見「多久才發現、多久才止血」。
- 根因是推論時，`root_cause.status` 用 `inferred`，並在 caveat 與解說中明說；不要把相關性寫成因果。
- 資料分析範例：儀表板數字歸零、指標突然翻倍、排程漏跑、重複匯入。

## metric

- 必要：`metric_name`、`definition`（`status` 必須是 `verified`，引用定義所在的 SQL、程式或指標字典）、`lineage`（1 至 12 個 `from` → `to` 的 `transform`）、`scope`（`grain`、`time_window`、`filters` 至少一項）。
- 可選 `comparison`：拿數字做前後比較時，`before` 與 `after` 都要有 evidence，否則驗證器擋下 `comparison_evidence_missing`。
- caveat 層固定回答「這個口徑在什麼情況下不能直接比」：時區、去重、篩選條件、定義變更日期。
- 資料分析範例：MAU、轉換率的分母、營收是否含退款、留存的起算日。

## 選 grammar 的快速規則

1. 使用者拿 log 或「為什麼壞了」來問：`incident`。
2. 使用者拿程式或 SQL 來問「這在做什麼」：`module`；如果焦點是「這個數字」而不是「這段程式」：`metric`。
3. 使用者問「選哪個」：`tradeoff`。
4. 其餘一律 `concept`。
5. 一次只回答一個問題；同時有兩個問題就做兩份 spec，不要硬塞進一個 grammar。
