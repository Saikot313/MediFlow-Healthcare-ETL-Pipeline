import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp(prefix="mediflow_airflow_"))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
os.environ.setdefault("AIRFLOW__CORE__LOAD_DEFAULT_CONNECTIONS", "False")
