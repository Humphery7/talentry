from __future__ import annotations

from pathlib import Path

# crawler/  (repo folder that contains data/, output/, src/)
CRAWLER_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = CRAWLER_ROOT / "data"
OUTPUT_DIR = CRAWLER_ROOT / "output"
