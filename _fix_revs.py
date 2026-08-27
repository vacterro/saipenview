from pathlib import Path
import re

root = Path(r"V:\___VAC\__K\__CODE\_PY\_SAIPENVIEW")

for name in ["saitest", "saipython", "saiui"]:
    outbox = root / ".saipen" / "extensions" / "subs" / name / "kitchen" / "OUTBOX.md"
    text = outbox.read_text(encoding="utf-8")
    charter = root / ".saipen" / "extensions" / "subs" / f"{name}.md"
    c_text = charter.read_text(encoding="utf-8")
    m = re.search(r'role_revision:\s*"([^"]+)"', c_text)
    rev = m.group(1) if m else ""
    new_text = re.sub(r"role_revision:\s*sha256:.*", f"role_revision: {rev}", text)
    outbox.write_text(new_text, encoding="utf-8")
    print(f"fixed {name}")
