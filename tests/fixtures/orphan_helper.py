import sys
import os
import time
import subprocess
from pathlib import Path

from saipenview.runtime import _assign_job_object

heartbeat = sys.argv[1]
marker = sys.argv[2]

child = subprocess.Popen([sys.executable, heartbeat], cwd=str(Path(heartbeat).parent))
_assign_job_object(child)
Path(marker).write_text(str(child.pid), encoding="utf-8")

# Brief moment so the heartbeat file is written at least once, then a hard
# ungraceful exit that must NOT leave the child alive (job object).
time.sleep(0.5)
os._exit(0)
