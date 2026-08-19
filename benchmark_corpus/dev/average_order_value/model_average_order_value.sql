SELECT
  customer_id,
  AVG(order_amount) AS avg_order_value
FROM orders
WHERE order_status = 'completed' AND is_test = false
GROUP BY customer_id