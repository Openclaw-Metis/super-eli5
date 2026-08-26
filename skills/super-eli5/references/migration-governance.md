# Migration Governance

本文件定義 super-eli5 名稱、邊界或安裝介面發生 lifecycle 變更時的最低治理要求。目前版本沒有進行 rename、deprecate、merge 或 split。

## Rename

保留舊名稱的 routing alias 至少一個 review interval，並在 release notes、安裝命令與 trigger eval 中加入舊名到新名的明確映射。不得靜默改名。

## Deprecate

先把 lifecycle status 設為 deprecated，指明 replacement、停止新增功能，並提供可執行的遷移步驟；仍在支援期內的安全與資料完整性問題必須修正。

## Merge

合併前列出兩個 skill 的 trigger、輸入、輸出與副作用映射；只有單一 primary job 仍成立時才能合併。衝突的輸出契約必須提供 adapter 或明列不相容。

## Split

拆分時依 primary job 切割，為每個新 skill 建立 negative triggers 與 handoff；舊入口只能作為薄 routing layer，不能維持兩份分歧實作。

## Compatibility

story spec、CLI 參數或 artifact 格式的 breaking change 必須提升對應版本、更新 verifier 與 fixtures，並提供舊 artifact 的明確支援範圍。無法向前相容時必須 fail closed。

## Migration Evidence

每次 lifecycle 變更至少保存：舊／新版本、trigger mapping、輸出差異、已知不相容、eval 結果、stage gate、publish gate 與 rollback 路徑。證據寫入 readiness report；人工判斷不得覆蓋機械 FAIL。
