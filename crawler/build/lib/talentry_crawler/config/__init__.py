"""Load WHAT to crawl and WHAT to look for, from data/*.csv. Never touches the internet."""

from .boards import load_boards
from .companies import load_companies
from .dictionaries import load_label_dictionaries
from .paths import DATA_DIR, OUTPUT_DIR

__all__ = [
    "DATA_DIR",
    "OUTPUT_DIR",
    "load_boards",
    "load_companies",
    "load_label_dictionaries",
]
