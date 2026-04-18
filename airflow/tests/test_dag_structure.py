import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(scope="module", autouse=True)
def _mock_external_services(): 
    patches = [
        patch("arxiv_ingestion.common.make_arxiv_client", return_value=MagicMock(max_results=10, base_url="http://mock")),
        patch("arxiv_ingestion.common.make_pdf_parser_service", return_value=MagicMock()),
        patch("arxiv_ingestion.common.make_database", return_value=MagicMock()),
        patch("arxiv_ingestion.common.make_opensearch_client", return_value=MagicMock()),
        patch("arxiv_ingestion.common.make_metadata_fetcher", return_value=MagicMock()),
        patch("arxiv_ingestion.indexing.make_database", return_value=MagicMock()),
        patch("arxiv_ingestion.indexing.make_hybrid_indexing_service", return_value=MagicMock()), 
        patch("arxiv_ingestion.indexing.make_opensearch_client_fresh", return_value=MagicMock()),
    ]
    for p in patches: 
        p.start()
    yield
    for p in patches: 
        p.stop()


@pytest.fixture(scope="module")
def dag(): 
    from airflow.models import DagBag

    dagbag = DagBag(dag_folder="airflow/dags/", include_examples=False)
    assert dagbag.import_errors == {}, f"DAG import errors: {dagbag.import_errors}"
    assert "arxiv_paper_ingestion" in dagbag.dags
    return dagbag.dags["arxiv_paper_ingestion"]

class TestDAGProperties: 
    """Validate top-level DAG configuration."""

    def test_dag_id(self, dag): 
        assert dag.dag_id == "arxiv_paper_ingestion"

    def test_schedule_weekdays_6am(self, dag): 
        assert dag.schedule == "0 6 * * 1-5"

    def test_owner(self, dag): 
        assert dag.default_args["owner"] == "production-agentic-rag"
    
    def test_max_active_run_is_one(self, dag): 
        assert dag.max_active_runs == 1
    
    def test_catchup_disabled(self, dag): 
        assert dag.catchup is False

    def test_retries(self, dag): 
        assert dag.default_args["retries"] == 2
    
    def test_tags(self, dag): 
        assert "arxiv" in dag.tags
        assert "ingestion" in dag.tags


class TestDAGTasks: 
    """Validate task definitions and dependencies."""

    EXPECTED_TASK_IDS = {
        "setup_environment",
        "fetch_daily_papers", 
        "index_papers_hybrid", 
        "generate_daily_report",
        "cleanup_temp_files",
    }

    def test_task_count(self, dag): 
        assert len(dag.tasks) == 5
    
    def test_task_expected_tasks_exist(self, dag): 
        actual_ids = {t.task_id for t in dag.tasks}
        assert actual_ids == self.EXPECTED_TASK_IDS

    def test_pipeline_order(self, dag): 
        """Verify linear pipeline: setup -> fetch -> index -> report -> cleanup."""
        expected_chain = [
            "setup_environment",
            "fetch_daily_papers", 
            "index_papers_hybrid", 
            "generate_daily_report", 
            "cleanup_temp_files", 
        ]
        for i in range(len(expected_chain) - 1):
            upstream =  dag.get_task(expected_chain[i])
            downstream = dag.get_task(expected_chain[i + 1])
            downstream_ids = [t.task_id for t in upstream.downstream_list]
            assert downstream.task_id in downstream_ids, (
                f"Expected {expected_chain[i]} -> {expected_chain[i + 1]}, "
                f"but downstream is {downstream_ids}"
            )
    
    def test_setup_has_no_upstream(self, dag): 
        setup = dag.get_task("setup_environment")
        assert len(setup.upstream_list) == 0
    
    def test_cleanup_has_no_downstream(self, dag): 
        cleanup = dag.get_task("cleanup_temp_files")
        assert len(cleanup.downstream_list) == 0
    
    def test_python_operators_tasks(self, dag): 
        from airflow.operators.python import PythonOperator

        for task_id in ["setup_environment", "fetch_daily_papers", "index_papers_hybrid", "generate_daily_report"]: 
            task = dag.get_task(task_id)
            assert isinstance(task, PythonOperator), f"{task_id} should be PythonOperator"
    
    def test_cleanup_is_bash_operator(self, dag): 
        from airflow.operators.bash import BashOperator

        cleanup = dag.get_task("cleanup_temp_files")
        assert isinstance(cleanup, BashOperator)
    




    