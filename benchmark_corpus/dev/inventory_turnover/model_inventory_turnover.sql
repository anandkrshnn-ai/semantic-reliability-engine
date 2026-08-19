SELECT
  warehouse_id,
  SUM(cogs) / SUM(stock_value) AS turnover_ratio
FROM inventory_movements
WHERE is_obsolete = false
GROUP BY warehouse_id