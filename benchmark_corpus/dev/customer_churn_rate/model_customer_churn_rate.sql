SELECT
  plan,
  COUNT(CASE WHEN cancelled = true THEN 1 END) * 1.0 / COUNT(*) AS churn_rate
FROM subscriptions
WHERE is_trial = false
GROUP BY plan