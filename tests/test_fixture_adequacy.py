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
