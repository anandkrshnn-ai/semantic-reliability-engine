SELECT
  priority,
  SUM(CASE WHEN resolved_within_sla = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS sla_rate
FROM support_tickets
WHERE is_spam = false
GROUP BY priority