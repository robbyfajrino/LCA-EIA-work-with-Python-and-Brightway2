import os
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

# Keep the Brightway project data out of the developer's home directory and CI cache.
os.environ.setdefault("BRIGHTWAY2_DIR", tempfile.mkdtemp(prefix="bw-test-"))
