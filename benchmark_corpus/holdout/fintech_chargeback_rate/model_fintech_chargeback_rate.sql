SELECT
  merchant_id,
  SUM(CASE WHEN is_disputed = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS chargeback_rate
FROM settled_payments
WHERE is_sandbox = false AND settlement_status = 'settled'
GROUP BY merchant_id