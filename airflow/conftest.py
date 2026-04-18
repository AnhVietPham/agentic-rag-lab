import sys
import os

# Add the airflow directory to sys.path so that "dags.xxx" imports work
sys.path.insert(0, os.path.dirname(__file__))
