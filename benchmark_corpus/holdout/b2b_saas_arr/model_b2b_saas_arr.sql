SELECT
  customer_id,
  SUM(mrr_amount * 12.0) AS annual_recurring_revenue
FROM saas_contracts
WHERE status = 'active' AND is_internal_account = false
GROUP BY customer_id