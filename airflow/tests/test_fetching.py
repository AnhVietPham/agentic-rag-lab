import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

from dags.arxiv_ingestion.fetching import fetch_daily_papers, run_paper_ingestion_pipeline

class TestFetchDailyPapersDateCalculation: 
    """Verify target date logic."""

    @patch("dags.arxiv_ingestion.fetching.asyncio.run")
    def test_target_date_is_yesterday_of_execution_date(self, mock_asyncio_run, mock_airflow_context): 
        """Execution_date=2026-02-10 -> target_date=2026-02-09"""
        mock_asyncio_run.return_value = {"papers_fetched": 0, "papers_stored": 0}

        result = fetch_daily_papers(**mock_airflow_context)

        assert result["date"] == "20260209"

    @patch("dags.arxiv_ingestion.fetching.asyncio.run")
    def test_target_date_crosses_month_boundary(self, mock_asyncio_run): 
        """execution_date=2025-09-01 -> target_date=20250831."""
        mock_asyncio_run.return_value = {"papers_fetched": 0, "papers_stored": 0}
        context = {
            "execution_date": datetime(2025, 9, 1, 6, 0, 0),
            "ti": MagicMock(),
        }
        result = fetch_daily_papers(**context)
        assert result["date"] == "20250831"
