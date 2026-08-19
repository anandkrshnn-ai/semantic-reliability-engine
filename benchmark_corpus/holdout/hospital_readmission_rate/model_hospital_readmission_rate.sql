SELECT
  department,
  SUM(CASE WHEN readmitted_30d = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS readmission_rate
FROM hospital_discharges
WHERE is_planned_readmission = false AND patient_deceased = false
GROUP BY department