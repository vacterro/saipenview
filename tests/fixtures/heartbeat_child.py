import sys
import time
import os
from pathlib import Path

hb = Path(sys.argv[1])
pid = os.getpid()
while True:
    hb.write_text(f"{pid} {time.time()}", encoding="utf-8")
    time.sleep(0.3)
