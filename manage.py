#!/usr/bin/env python
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kairo.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
