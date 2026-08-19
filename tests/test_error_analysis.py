import pytest
from semantic_reliability.harness.error_analysis import SurvivingDefectTaxonomy, RootCauseCategory, SeverityLevel


def test_surviving_defect_taxonomy_validation():
    defects = SurvivingDefectTaxonomy.get_defect_analysis()
    assert len(defects) >= 4

    categories = {d.root_cause_category for d in defects}
    assert RootCauseCategory.MISSING_CONTRACT in categories
    assert RootCauseCategory.ASSERTION_GAP in categories
    assert RootCauseCategory.MUTATION_ORACLE_GAP in categories

    for d in defects:
        assert d.mutation_id.strip() != ""
        assert d.model.strip() != ""
        assert d.recommended_assertion.strip() != ""
        assert isinstance(d.severity, SeverityLevel)
