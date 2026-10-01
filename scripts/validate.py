"""호환용 래퍼 — 엔진은 engine/ 로 옮겼다. `python3 faultline.py validate` 를 쓴다."""
import os
import subprocess
import sys

CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "faultline.py")
sys.exit(subprocess.call([sys.executable, CLI, "validate"] + sys.argv[1:]))
