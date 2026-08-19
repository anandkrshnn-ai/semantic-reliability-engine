"""Scaffolds the 8-model canonical analytical benchmark corpus."""
from pathlib import Path
import yaml
import textwrap

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "benchmark_corpus"
CORPUS_ROOT.mkdir(parents=True, exist_ok=True)

MODELS = [
    {
        "id": "net_revenue",
        "name": "Net Revenue",
        "description": "Recognized revenue minus refunds for active enterprise users in NA",
        "table": "transactions",
        "csv_header": "transaction_id,customer_id,transaction_date,amount,type,status,region,last_login",
        "csv_rows": [
            "T1,C1,2026-01-05 10:00:00,1000.0,invoice,active,NA,2026-08-01",
            "T2,C1,2026-01-12 11:30:00,200.0,refund,active,NA,2026-08-01",
            "T3,C2,2026-01-15 09:15:00,2500.0,invoice,active,NA,2026-08-10",
            "T4,C2,2026-01-20 14:00:00,500.0,refund,active,NA,2026-08-10",
            "T5,C3,2026-01-18 16:45:00,3000.0,invoice,pending,NA,2026-05-01",
            "T6,C4,2026-01-22 12:00:00,4500.0,invoice,active,EU,2026-08-12",
        ],
        "sql": """SELECT
  customer_id,
  DATE_TRUNC('month', transaction_date) AS reporting_month,
  SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
  SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
FROM transactions
WHERE region = 'NA' AND status = 'active'
GROUP BY customer_id, DATE_TRUNC('month', transaction_date)""",
        "contract": {
            "metric": "net_revenue",
            "owner": "finance",
            "grain": "customer_month",
            "invariants": {
                "population": {"required_filters": ["status = 'active'", "region = 'NA'"]},
                "aggregation": {"positive_components": ["type = 'invoice'"], "negative_components": ["type = 'refund'"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["customer_id", "reporting_month", "net_revenue"]},
            {"type": "required_population", "source_table": "transactions", "required_filter": "status = 'active'"},
            {"type": "required_population", "source_table": "transactions", "required_filter": "region = 'NA'"},
            {"type": "metric_value", "column": "net_revenue", "expected": 2800.0, "tolerance_pct": 5.0}
        ]
    },
    {
        "id": "monthly_active_users",
        "name": "Monthly Active Users (MAU)",
        "description": "Unique count of active authenticated users engaging within 30 days",
        "table": "user_logins",
        "csv_header": "user_id,login_date,status,is_bot,region",
        "csv_rows": [
            "U1,2026-01-10 09:00:00,active,false,NA",
            "U1,2026-01-15 14:00:00,active,false,NA",
            "U2,2026-01-12 11:00:00,active,false,EU",
            "U3,2026-01-20 16:30:00,suspended,false,NA",
            "U4,2026-01-22 18:00:00,active,true,NA",
            "U5,2026-01-25 10:15:00,active,false,NA",
        ],
        "sql": """SELECT
  DATE_TRUNC('month', login_date) AS reporting_month,
  COUNT(DISTINCT user_id) AS active_users
FROM user_logins
WHERE status = 'active' AND is_bot = false
GROUP BY DATE_TRUNC('month', login_date)""",
        "contract": {
            "metric": "monthly_active_users",
            "owner": "product",
            "grain": "monthly",
            "invariants": {
                "population": {"required_filters": ["status = 'active'", "is_bot = false"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["reporting_month", "active_users"]},
            {"type": "required_population", "source_table": "user_logins", "required_filter": "is_bot = false", "join_key": "user_id"},
            {"type": "metric_value", "column": "active_users", "expected": 3.0}
        ]
    },
    {
        "id": "customer_churn_rate",
        "name": "Customer Churn Rate",
        "description": "Proportion of active subscription cancellations per cohort",
        "table": "subscriptions",
        "csv_header": "sub_id,customer_id,start_date,cancelled,is_trial,plan",
        "csv_rows": [
            "S1,C1,2026-01-01,false,false,pro",
            "S2,C2,2026-01-01,true,false,pro",
            "S3,C3,2026-01-01,false,false,enterprise",
            "S4,C4,2026-01-01,true,true,free_trial",
            "S5,C5,2026-01-01,false,false,pro",
        ],
        "sql": """SELECT
  plan,
  COUNT(CASE WHEN cancelled = true THEN 1 END) * 1.0 / COUNT(*) AS churn_rate
FROM subscriptions
WHERE is_trial = false
GROUP BY plan""",
        "contract": {
            "metric": "customer_churn_rate",
            "owner": "growth",
            "grain": "plan",
            "invariants": {
                "population": {"required_filters": ["is_trial = false"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["plan", "churn_rate"]},
            {"type": "required_population", "source_table": "subscriptions", "required_filter": "is_trial = false", "join_key": "customer_id"},
            {"type": "metric_value", "column": "churn_rate", "min_value": 0.0, "max_value": 1.0}
        ]
    },
    {
        "id": "average_order_value",
        "name": "Average Order Value (AOV)",
        "description": "Mean value of completed, non-fraudulent purchase orders",
        "table": "orders",
        "csv_header": "order_id,customer_id,order_date,order_amount,order_status,is_test",
        "csv_rows": [
            "O1,C1,2026-01-05,100.0,completed,false",
            "O2,C2,2026-01-06,200.0,completed,false",
            "O3,C3,2026-01-07,300.0,completed,false",
            "O4,C4,2026-01-08,500.0,cancelled,false",
            "O5,C5,2026-01-09,10000.0,completed,true",
        ],
        "sql": """SELECT
  customer_id,
  AVG(order_amount) AS avg_order_value
FROM orders
WHERE order_status = 'completed' AND is_test = false
GROUP BY customer_id""",
        "contract": {
            "metric": "average_order_value",
            "owner": "ecommerce",
            "grain": "customer",
            "invariants": {
                "population": {"required_filters": ["order_status = 'completed'", "is_test = false"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["customer_id", "avg_order_value"]},
            {"type": "required_population", "source_table": "orders", "required_filter": "is_test = false", "join_key": "customer_id"},
            {"type": "metric_value", "column": "avg_order_value", "max_value": 1000.0}
        ]
    },
    {
        "id": "inventory_turnover",
        "name": "Inventory Stock Turnover",
        "description": "Ratio of Cost of Goods Sold to average ending inventory value",
        "table": "inventory_movements",
        "csv_header": "sku,warehouse_id,cogs,stock_value,is_obsolete",
        "csv_rows": [
            "SKU-A,WH-1,50000.0,10000.0,false",
            "SKU-B,WH-1,20000.0,5000.0,false",
            "SKU-C,WH-2,80000.0,20000.0,false",
            "SKU-D,WH-2,0.0,15000.0,true",
        ],
        "sql": """SELECT
  warehouse_id,
  SUM(cogs) / SUM(stock_value) AS turnover_ratio
FROM inventory_movements
WHERE is_obsolete = false
GROUP BY warehouse_id""",
        "contract": {
            "metric": "inventory_turnover",
            "owner": "supply_chain",
            "grain": "warehouse",
            "invariants": {
                "population": {"required_filters": ["is_obsolete = false"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["warehouse_id", "turnover_ratio"]},
            {"type": "metric_value", "column": "turnover_ratio", "min_value": 1.0}
        ]
    },
    {
        "id": "sla_compliance_rate",
        "name": "SLA Compliance Rate",
        "description": "Percentage of support tickets resolved within contracted SLA window",
        "table": "support_tickets",
        "csv_header": "ticket_id,agent_id,resolved_within_sla,is_spam,priority",
        "csv_rows": [
            "T1,A1,true,false,high",
            "T2,A1,true,false,high",
            "T3,A2,false,false,medium",
            "T4,A2,true,false,low",
            "T5,A3,false,true,low",
        ],
        "sql": """SELECT
  priority,
  SUM(CASE WHEN resolved_within_sla = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS sla_rate
FROM support_tickets
WHERE is_spam = false
GROUP BY priority""",
        "contract": {
            "metric": "sla_compliance_rate",
            "owner": "customer_support",
            "grain": "priority",
            "invariants": {
                "population": {"required_filters": ["is_spam = false"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["priority", "sla_rate"]},
            {"type": "metric_value", "column": "sla_rate", "min_value": 0.0, "max_value": 1.0}
        ]
    },
    {
        "id": "checkout_conversion_rate",
        "name": "Checkout Conversion Rate",
        "description": "Ratio of completed checkouts to checkout sessions started",
        "table": "checkout_events",
        "csv_header": "session_id,user_id,event_name,is_internal_ip",
        "csv_rows": [
            "S1,U1,checkout_complete,false",
            "S2,U2,checkout_start,false",
            "S3,U3,checkout_complete,false",
            "S4,U4,checkout_complete,true",
        ],
        "sql": """SELECT
  COUNT(CASE WHEN event_name = 'checkout_complete' THEN 1 END) * 1.0 / COUNT(*) AS conversion_rate
FROM checkout_events
WHERE is_internal_ip = false""",
        "contract": {
            "metric": "checkout_conversion_rate",
            "owner": "marketing",
            "grain": "aggregate",
            "invariants": {
                "population": {"required_filters": ["is_internal_ip = false"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["conversion_rate"]},
            {"type": "metric_value", "column": "conversion_rate", "min_value": 0.0, "max_value": 1.0}
        ]
    },
    {
        "id": "customer_retention_rate",
        "name": "Customer Retention Rate",
        "description": "Percentage of active cohort returning in subsequent period",
        "table": "retention_cohorts",
        "csv_header": "cohort_id,customer_id,returned_next_period,status",
        "csv_rows": [
            "2026-Q1,C1,true,active",
            "2026-Q1,C2,true,active",
            "2026-Q1,C3,false,active",
            "2026-Q1,C4,false,banned",
        ],
        "sql": """SELECT
  cohort_id,
  SUM(CASE WHEN returned_next_period = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS retention_rate
FROM retention_cohorts
WHERE status = 'active'
GROUP BY cohort_id""",
        "contract": {
            "metric": "customer_retention_rate",
            "owner": "analytics",
            "grain": "cohort",
            "invariants": {
                "population": {"required_filters": ["status = 'active'"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["cohort_id", "retention_rate"]},
            {"type": "metric_value", "column": "retention_rate", "min_value": 0.0, "max_value": 1.0}
        ]
    }
]

for m in MODELS:
    m_dir = CORPUS_ROOT / m["id"]
    m_dir.mkdir(parents=True, exist_ok=True)

    # 1. Base SQL
    (m_dir / f"model_{m['id']}.sql").write_text(m["sql"], encoding="utf-8")

    # 2. Metric Contract YAML
    contract_data = m["contract"]
    contract_data["sql"] = m["sql"]
    contract_data["description"] = m["description"]
    (m_dir / "contract.yaml").write_text(yaml.dump(contract_data, sort_keys=False), encoding="utf-8")

    # 3. Fixture CSV
    csv_content = m["csv_header"] + "\n" + "\n".join(m["csv_rows"]) + "\n"
    (m_dir / f"{m['table']}.csv").write_text(csv_content, encoding="utf-8")

    # 4. Standard dbt schema.yml
    dbt_schema = {
        "version": 2,
        "models": [{
            "name": f"model_{m['id']}",
            "columns": [{"name": col, "tests": ["not_null"]} for col in m["semantic_assertions"][0]["columns"]]
        }]
    }
    (m_dir / "schema.yml").write_text(yaml.dump(dbt_schema, sort_keys=False), encoding="utf-8")

    # 5. Semantic assertions YAML
    sem_schema = {
        "suite_name": f"semantic_{m['id']}",
        "assertions": m["semantic_assertions"]
    }
    (m_dir / "semantic_assertions.yaml").write_text(yaml.dump(sem_schema, sort_keys=False), encoding="utf-8")

print(f"Scaffolded {len(MODELS)} benchmark corpus models at {CORPUS_ROOT}")
