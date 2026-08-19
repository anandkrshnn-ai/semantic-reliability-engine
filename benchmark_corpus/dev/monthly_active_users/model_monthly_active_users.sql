SELECT
  DATE_TRUNC('month', login_date) AS reporting_month,
  COUNT(DISTINCT user_id) AS active_users
FROM user_logins
WHERE status = 'active' AND is_bot = false
GROUP BY DATE_TRUNC('month', login_date)