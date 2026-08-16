"""Regression of approved BI metrics against the official hackathon dataset."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bi_agent.service import BIService

DATASET_VALUE = os.getenv("SONIA_BI_OFFICIAL_DATASET_PATH")
DATASET = Path(DATASET_VALUE) if DATASET_VALUE else None


@pytest.mark.official_dataset
@pytest.mark.skipif(
    not DATASET or not DATASET.exists(),
    reason="Define SONIA_BI_OFFICIAL_DATASET_PATH.",
)
def test_approved_metrics_remain_equivalent_at_july_cutoff() -> None:
    assert DATASET is not None
    service = BIService(DATASET)
    executive = service.executive_snapshot("2026-07-31")
    risk = service.risk_concentration("SEGMENTO_PAIS", "overdue_balance", 10, "2026-07-31")
    recovery = service.recovery_intelligence("2026-07-31")
    insights = service.management_insights("2026-07-31")
    quality = service.data_quality_report("2026-07-31")

    assert executive["metrics"]["outstanding_balance"] == 155600.57
    assert executive["metrics"]["overdue_balance"] == 147175.97
    assert risk["metrics"]["metric_total"] == 147175.97
    assert recovery["metrics"]["addressable_exposure"] == 125503.95
    assert insights["metrics"]["top_n_customer_coverage"] == 0.85
    assert quality["metrics"]["unmatched_payment_count"] == 74
    responses = (executive, risk, recovery, insights, quality)
    assert all(response["contract_version"] == "1.0" for response in responses)
