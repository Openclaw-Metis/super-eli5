# 人工審查筆記範本

本檔只記錄尚無法安全機械判定的 reviewer judgment，不得當成發布證據。完成後把可驗證結論與證據寫入 `references/readiness_report.md`。

## 邊界審查
- 本 skill 是否只做「證據誠實的超白話解說」這一件事？有沒有偷偷長成文件產生器或研究工具？
- 與 `mermaid-diagram`、`humanize-text`、`knowledge-framework`、`slide-studio`、`deep-research` 的交棒是否清楚？
- 新使用者能否從 description 判斷「只要畫圖」或「只要改語氣」時不該用本 skill？

## 觸發審查
- Trigger examples 是否貼近資料分析師真實的說法（口徑、血緣、儀表板、日報）？
- 是否涵蓋繁體中文、英文與混合語言（「幫我 ELI5 一下 batch vs streaming」）？

## 解說品質審查
- 一句話版能否被五歲小孩或只讀第一行的主管複述？
- 類比的失真點是否指出真正會誤導的地方？
- 三層真相的「但要注意」是否寫真實會被誤用的情境，而非形式免責？
- 推論在文字中是否聽得出是推論？根因、定義、建議是否沒有類比混入？

## 證據審查
- 每筆 verified 是否真的打開過來源？quote 是否逐字？URL 是否有 retrieved_at？
- `--bind` 後的檢驗等級是否與交付訊息一致？
- locator 與 quote 是否含使用者名稱、絕對路徑、內部主機名或機密數字？

## Artifact 審查
- 瀏覽器實際開啟：桌面與 390px 寬度各一次，場景圖無裁切、trace 可切換、教回來可展開。
- 這一項沒有自動化；未執行時在 readiness report 標記為未執行，不得宣稱已檢視。

## 維護審查
- 是否應 rename、merge、split、deprecate 或 retire？
- scripts 的 validator、renderer、verifier 版本號是否同步更新？
