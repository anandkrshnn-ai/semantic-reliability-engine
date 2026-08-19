SELECT
  customer_id,
  DATE_TRUNC('month', transaction_date) AS reporting_month,
  SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
  SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
FROM transactions
WHERE region = 'NA' AND status = 'active'
GROUP BY customer_id, DATE_TRUNC('month', transaction_date)