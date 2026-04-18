from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.bash import BashOperator


def _setup():
    from arxiv_ingestion.setup import setup_environment
    return setup_environment()


def _fetch():
    from arxiv_ingestion.fetching import fetch_daily_papers
    return fetch_daily_papers()


def _index():
    from arxiv_ingestion.indexing import index_papers_hybrid
    return index_papers_hybrid()


def _report():
    from arxiv_ingestion.reporting import generate_daily_report
    return generate_daily_report()

# Default DAG arguments (passed to each operator unless overridden)
default_args = {
    "owner": "production-agentic-rag",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=30),
}

with DAG(
    dag_id="arxiv_paper_ingestion",
    description=(
        "Daily arXiv CS.AI paper pipeline: "
        "fetch → store to PostgreSQL → chunk & embed → hybrid OpenSearch indexing"
    ),
    default_args=default_args,
    schedule="0 6 * * 1-5",
    start_date=datetime(2026, 2, 10),
    catchup=False,
    max_active_runs=1,
    tags=["arxiv", "papers", "ingestion", "hybrid-search", "embeddings", "chunks"],
) as dag:
    setup_task = PythonOperator(
        task_id="setup_environment",
        python_callable=_setup,
    )

    fetch_task = PythonOperator(
        task_id="fetch_daily_papers",
        python_callable=_fetch,
    )

    index_hybrid_task = PythonOperator(
        task_id="index_papers_hybrid",
        python_callable=_index,
    )

    report_task = PythonOperator(
        task_id="generate_daily_report",
        python_callable=_report,
    )

    cleanup_task = BashOperator(
        task_id="cleanup_temp_files",
        bash_command="""
        echo "Cleaning up temporary files..."
        find /tmp -name "*.pdf" -type f -mtime +30 -delete 2>/dev/null || true
        echo "Cleanup completed"
        """,
    )

    setup_task >> fetch_task >> index_hybrid_task >> report_task >> cleanup_task
