from pathlib import Path
import re

root = Path(r"V:\___VAC\__K\__CODE\_PY\_SAIPENVIEW")
new_fp = "git-delta-v1:a1f4a605192a4ab99161c8a994fdfabc48b85a7d9fa4247727cf4867ff8018cf"
new_head = "5b18d1710901485961c1a44a995140bcc549b40a"

for name in ["saihunt", "saitest", "saipython", "saiui"]:
    outbox = root / ".saipen" / "extensions" / "subs" / name / "kitchen" / "OUTBOX.md"
    if outbox.exists():
        text = outbox.read_text(encoding="utf-8")
        new_text = re.sub(r'source_head:\s*\S+', f"source_head: {new_head}", text)
        new_text = re.sub(r'source_tree_fingerprint:\s*\S+', f"source_tree_fingerprint: {new_fp}", new_text)
        outbox.write_text(new_text, encoding="utf-8")
        print(f"updated {name}")
