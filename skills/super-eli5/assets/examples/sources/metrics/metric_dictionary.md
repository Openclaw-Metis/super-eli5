# 指標字典（節錄）

## MAU（Monthly Active Users）

- 粒度：自然月，時區 Asia/Taipei。
- 定義：當月至少產生一次有效事件的去重 user_id 數。
- 有效事件：session_start、purchase、content_view。
- 排除：internal_flag = true 的內部測試帳號。
- 注意：2026-07-01 起 content_view 才納入有效事件；之前只算 session_start 與 purchase，因此 7 月前後不可直接比較。
