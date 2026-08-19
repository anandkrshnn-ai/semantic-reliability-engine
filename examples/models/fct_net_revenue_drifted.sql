-- Drifted Model: Developer shifted 'status = active' to 'last_login > 30 days' and dropped refund subtraction
SELECT
  customer_id,
  DATE_TRUNC('month', transaction_date) AS reporting_month,
  SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) AS net_revenue
FROM transactions
WHERE region = 'NA' AND last_login >= CURRENT_DATE - INTERVAL '30' DAY
GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
