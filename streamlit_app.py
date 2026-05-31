import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

import app.app  # noqa: F401
