-- 月活躍用戶（MAU）定義：當月至少有一次「有效事件」的去重 user_id 數
-- 有效事件：event_name IN ('session_start', 'purchase', 'content_view')
-- 排除：internal_flag = true 的內部測試帳號
WITH monthly_events AS (
  SELECT
    DATE_TRUNC('month', event_time AT TIME ZONE 'Asia/Taipei') AS month,
    user_id
  FROM analytics.events
  WHERE event_name IN ('session_start', 'purchase', 'content_view')
    AND internal_flag = false
)
SELECT month, COUNT(DISTINCT user_id) AS mau
FROM monthly_events
GROUP BY month
ORDER BY month;
