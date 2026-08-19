"""Scaffolds the 6-model frozen holdout analytical benchmark corpus with Tier-2 realistic fixtures."""
from pathlib import Path
import shutil
import yaml

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "benchmark_corpus"
DEV_ROOT = CORPUS_ROOT / "dev"
HOLDOUT_ROOT = CORPUS_ROOT / "holdout"

DEV_ROOT.mkdir(parents=True, exist_ok=True)
HOLDOUT_ROOT.mkdir(parents=True, exist_ok=True)

# 1. Move any top-level dev models into benchmark_corpus/dev/
for item in CORPUS_ROOT.iterdir():
    if item.is_dir() and item.name not in ("dev", "holdout"):
        dest = DEV_ROOT / item.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(item), str(DEV_ROOT))

# 2. Define the 6 Holdout Models with Tier-2 Realistic Fixtures
HOLDOUT_MODELS = [
    {
        "id": "b2b_saas_arr",
        "name": "B2B SaaS Annual Recurring Revenue (ARR)",
        "description": "Normalized annual recurring contract value across active enterprise subscriptions",
        "table": "saas_contracts",
        "csv_header": "contract_id,customer_id,mrr_amount,contract_term_months,status,is_internal_account,billing_frequency",
        "csv_rows": [
            "CTR-101,ACME-CORP,5000.0,12,active,false,annual",
            "CTR-102,ACME-CORP,1000.0,12,active,false,annual",  # expansion add-on
            "CTR-103,BETA-LLC,12000.0,24,active,false,annual",
            "CTR-104,GAMMA-INC,2500.0,12,churned,false,monthly",
            "CTR-105,DELTA-INTERNAL,10000.0,12,active,true,annual",  # internal test
            "CTR-106,EPSILON-CO,8000.0,12,active,false,annual",
        ],
        "sql": """SELECT
  customer_id,
  SUM(mrr_amount * 12.0) AS annual_recurring_revenue
FROM saas_contracts
WHERE status = 'active' AND is_internal_account = false
GROUP BY customer_id""",
        "contract": {
            "metric": "b2b_saas_arr",
            "owner": "finance_revops",
            "grain": "customer",
            "invariants": {
                "population": {"required_filters": ["status = 'active'", "is_internal_account = false"]},
                "grain": {"required_dimensions": ["customer_id"]},
                "aggregation": {"required_function": "SUM"},
                "units": {"currency": "USD"}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["customer_id", "annual_recurring_revenue"]},
            {"type": "required_population", "source_table": "saas_contracts", "required_filter": "status = 'active'"},
            {"type": "required_population", "source_table": "saas_contracts", "required_filter": "is_internal_account = false"},
            {"type": "metric_value", "column": "annual_recurring_revenue", "expected": 312000.0, "tolerance_pct": 5.0}
        ]
    },
    {
        "id": "fintech_chargeback_rate",
        "name": "Fintech Dispute / Chargeback Rate",
        "description": "Proportion of settled transactions flagged as disputed or fraudulent",
        "table": "settled_payments",
        "csv_header": "payment_id,merchant_id,amount,is_disputed,is_sandbox,settlement_status",
        "csv_rows": [
            "PAY-01,MERCH-1,100.0,false,false,settled",
            "PAY-02,MERCH-1,250.0,true,false,settled",
            "PAY-03,MERCH-2,500.0,false,false,settled",
            "PAY-04,MERCH-2,1200.0,false,false,settled",
            "PAY-05,MERCH-3,80.0,true,false,settled",
            "PAY-06,MERCH-4,9999.0,true,true,settled",  # sandbox test
        ],
        "sql": """SELECT
  merchant_id,
  SUM(CASE WHEN is_disputed = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS chargeback_rate
FROM settled_payments
WHERE is_sandbox = false AND settlement_status = 'settled'
GROUP BY merchant_id""",
        "contract": {
            "metric": "fintech_chargeback_rate",
            "owner": "risk_compliance",
            "grain": "merchant",
            "invariants": {
                "population": {"required_filters": ["is_sandbox = false", "settlement_status = 'settled'"]},
                "grain": {"required_dimensions": ["merchant_id"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["merchant_id", "chargeback_rate"]},
            {"type": "required_population", "source_table": "settled_payments", "required_filter": "is_sandbox = false", "join_key": "merchant_id"},
            {"type": "metric_value", "column": "chargeback_rate", "min_value": 0.0, "max_value": 1.0}
        ]
    },
    {
        "id": "marketplace_take_rate",
        "name": "Marketplace Net Take Rate",
        "description": "Platform net commission fee revenue divided by Gross Merchandise Value",
        "table": "marketplace_orders",
        "csv_header": "order_id,seller_id,gmv_amount,commission_fee,is_cancelled,is_test_order",
        "csv_rows": [
            "ORD-1,SEL-A,1000.0,150.0,false,false",
            "ORD-2,SEL-A,2000.0,300.0,false,false",
            "ORD-3,SEL-B,500.0,75.0,false,false",
            "ORD-4,SEL-C,10000.0,1500.0,true,false",  # cancelled
            "ORD-5,SEL-D,50000.0,7500.0,false,true",  # test
        ],
        "sql": """SELECT
  seller_id,
  SUM(commission_fee) / SUM(gmv_amount) AS take_rate
FROM marketplace_orders
WHERE is_cancelled = false AND is_test_order = false
GROUP BY seller_id""",
        "contract": {
            "metric": "marketplace_take_rate",
            "owner": "marketplace_ops",
            "grain": "seller",
            "invariants": {
                "population": {"required_filters": ["is_cancelled = false", "is_test_order = false"]},
                "grain": {"required_dimensions": ["seller_id"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["seller_id", "take_rate"]},
            {"type": "metric_value", "column": "take_rate", "min_value": 0.05, "max_value": 0.30}
        ]
    },
    {
        "id": "cloud_compute_burn_rate",
        "name": "Cloud Compute Cost Burn Rate",
        "description": "Total cloud infrastructure compute cost after spot instance credits",
        "table": "cloud_instance_usage",
        "csv_header": "instance_id,team,instance_hours,hourly_rate,spot_discount_credit,is_benchmark_run",
        "csv_rows": [
            "I-1,core-ai,100.0,4.50,50.0,false",
            "I-2,core-ai,200.0,4.50,100.0,false",
            "I-3,web-api,50.0,1.20,0.0,false",
            "I-4,benchmark-job,500.0,8.00,0.0,true",  # benchmark run
        ],
        "sql": """SELECT
  team,
  SUM(instance_hours * hourly_rate) - SUM(spot_discount_credit) AS net_compute_cost
FROM cloud_instance_usage
WHERE is_benchmark_run = false
GROUP BY team""",
        "contract": {
            "metric": "cloud_compute_burn_rate",
            "owner": "finops",
            "grain": "team",
            "invariants": {
                "population": {"required_filters": ["is_benchmark_run = false"]},
                "grain": {"required_dimensions": ["team"]},
                "aggregation": {"positive_components": ["instance_hours"], "negative_components": ["spot_discount_credit"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["team", "net_compute_cost"]},
            {"type": "metric_value", "column": "net_compute_cost", "expected": 1260.0, "tolerance_pct": 5.0}
        ]
    },
    {
        "id": "hospital_readmission_rate",
        "name": "Hospital 30-Day Readmission Rate",
        "description": "Percentage of discharged inpatients readmitted within 30 days excluding planned procedures",
        "table": "hospital_discharges",
        "csv_header": "admission_id,department,readmitted_30d,is_planned_readmission,patient_deceased",
        "csv_rows": [
            "ADM-1,cardiology,true,false,false",
            "ADM-2,cardiology,false,false,false",
            "ADM-3,orthopedics,true,true,false",  # planned
            "ADM-4,orthopedics,false,false,false",
            "ADM-5,cardiology,true,false,true",   # deceased
        ],
        "sql": """SELECT
  department,
  SUM(CASE WHEN readmitted_30d = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS readmission_rate
FROM hospital_discharges
WHERE is_planned_readmission = false AND patient_deceased = false
GROUP BY department""",
        "contract": {
            "metric": "hospital_readmission_rate",
            "owner": "clinical_quality",
            "grain": "department",
            "invariants": {
                "population": {"required_filters": ["is_planned_readmission = false", "patient_deceased = false"]},
                "grain": {"required_dimensions": ["department"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["department", "readmission_rate"]},
            {"type": "metric_value", "column": "readmission_rate", "min_value": 0.0, "max_value": 1.0}
        ]
    },
    {
        "id": "ad_campaign_roas",
        "name": "Ad Campaign Return on Ad Spend (ROAS)",
        "description": "Attributed conversion sales divided by gross media spend",
        "table": "ad_campaign_performance",
        "csv_header": "campaign_id,channel,attributed_revenue,ad_spend,is_test_campaign",
        "csv_rows": [
            "CMP-1,paid_search,50000.0,10000.0,false",
            "CMP-2,paid_search,80000.0,20000.0,false",
            "CMP-3,social_ads,30000.0,15000.0,false",
            "CMP-4,staging_test,100.0,5000.0,true",  # test
        ],
        "sql": """SELECT
  channel,
  SUM(attributed_revenue) / SUM(ad_spend) AS roas
FROM ad_campaign_performance
WHERE is_test_campaign = false
GROUP BY channel""",
        "contract": {
            "metric": "ad_campaign_roas",
            "owner": "performance_marketing",
            "grain": "channel",
            "invariants": {
                "population": {"required_filters": ["is_test_campaign = false"]},
                "grain": {"required_dimensions": ["channel"]}
            }
        },
        "semantic_assertions": [
            {"type": "not_null", "columns": ["channel", "roas"]},
            {"type": "metric_value", "column": "roas", "min_value": 1.0, "max_value": 10.0}
        ]
    }
]

for m in HOLDOUT_MODELS:
    m_dir = HOLDOUT_ROOT / m["id"]
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

print(f"Scaffolded 6 Holdout models in {HOLDOUT_ROOT}")
