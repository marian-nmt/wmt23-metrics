from pathlib import Path
import logging as log

log.basicConfig(level=log.INFO)


class Config:

    #BLOB_ROOT = '/mnt/tg/projects/mt-metrics/2023-metric-distill/evals'
    BLOB_ROOT = Path.home() / '.mt-metrics-eval'
    METRICS_BASE_DIR = f'{BLOB_ROOT}/mt-metrics-eval-v2'
    METRICS_USER_DIR = f'{BLOB_ROOT}/user-metrics'
    DEF_PATHS = [METRICS_BASE_DIR, METRICS_USER_DIR]
    PBAR_ENABLED = True
