SELECT
  seller_id,
  SUM(commission_fee) / SUM(gmv_amount) AS take_rate
FROM marketplace_orders
WHERE is_cancelled = false AND is_test_order = false
GROUP BY seller_id