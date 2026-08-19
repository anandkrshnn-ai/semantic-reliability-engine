SELECT
  team,
  SUM(instance_hours * hourly_rate) - SUM(spot_discount_credit) AS net_compute_cost
FROM cloud_instance_usage
WHERE is_benchmark_run = false
GROUP BY team