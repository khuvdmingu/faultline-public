"""호환용 래퍼 — 서버는 앱 루트의 server.py 로 옮겼다."""
import os
import runpy
import sys

sys.argv[0] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server.py")
runpy.run_path(sys.argv[0], run_name="__main__")
