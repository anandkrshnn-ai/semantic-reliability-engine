SELECT
  COUNT(CASE WHEN event_name = 'checkout_complete' THEN 1 END) * 1.0 / COUNT(*) AS conversion_rate
FROM checkout_events
WHERE is_internal_ip = false