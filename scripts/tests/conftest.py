import sys
from pathlib import Path

# scripts/ is a dev-tools dir, not a uv workspace package, so put it on the path
# to import the dev modules under test (e.g. _fsstore).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
