import sys
from pathlib import Path

# The service runs with src/ on the path (`uvicorn app:app` from src/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "talentry_embeddings"))
