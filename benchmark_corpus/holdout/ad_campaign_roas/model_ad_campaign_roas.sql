SELECT
  channel,
  SUM(attributed_revenue) / SUM(ad_spend) AS roas
FROM ad_campaign_performance
WHERE is_test_campaign = false
GROUP BY channel