import pytest
import duckdb
from semantic_reliability.harness.fixture_adequacy import FixtureAdequacyChecker


def test_fixture_adequacy_full():
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE transactions (
            customer_id VARCHAR,
            status VARCHAR,
            region VARCHAR,
            amount DOUBLE
        );
        INSERT INTO transactions VALUES
        ('C1', 'active', 'NA', 1000.0),
        ('C1', 'active', 'EU', 500.0),
        ('C2', 'inactive', 'NA', 200.0),
        ('C3', 'active', 'APAC', 800.0);
    """)

    report = FixtureAdequacyChecker.audit_fixture(con, "transactions")
    assert report.total_rows == 4
    assert report.is_adequate is True
    assert report.adequacy_score_pct >= 70.0


def test_fixture_adequacy_missing_status_contrast():
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE single_status (
            customer_id VARCHAR,
            status VARCHAR,
            amount DOUBLE
        );
        INSERT INTO single_status VALUES
        ('C1', 'active', 100.0),
        ('C2', 'active', 200.0);
    """)

    report = FixtureAdequacyChecker.audit_fixture(con, "single_status")
    status_check = next(c for c in report.checks if "Status Contrast" in c.check_name)
    assert status_check.status == "FAIL"

def test_fixture_adequacy_recognizes_typed_columns_without_name_list_match():
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE marketplace_orders (
            order_id VARCHAR, seller_id VARCHAR, gmv_amount DOUBLE, commission_fee DOUBLE,
            is_cancelled BOOLEAN, is_test_order BOOLEAN
        );
        INSERT INTO marketplace_orders VALUES
        ('ORD-1','SEL-A',1000.0,150.0,false,false),
        ('ORD-2','SEL-A',2000.0,200.0,false,false),
        ('ORD-3','SEL-B',500.0,75.0,false,false),
        ('ORD-4','SEL-C',10000.0,2000.0,true,false),
        ('ORD-5','SEL-D',50000.0,2500.0,false,true);
    """)
    report = FixtureAdequacyChecker.audit_fixture(con, "marketplace_orders")
    assert report.adequacy_score_pct >= 80.0
    assert any(c.check_name == "Boolean Flag Contrast" and c.status == "PASS" for c in report.checks)
