SELECT
  cohort_id,
  SUM(CASE WHEN returned_next_period = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS retention_rate
FROM retention_cohorts
WHERE status = 'active'
GROUP BY cohort_id