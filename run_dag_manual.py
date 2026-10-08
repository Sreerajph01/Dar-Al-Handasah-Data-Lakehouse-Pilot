import sys
sys.path.append('uc2-warehouse-migration/dags')
from uc2_ingest_bronze import load_apis_to_iceberg
load_apis_to_iceberg()
