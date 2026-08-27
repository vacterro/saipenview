from pathlib import Path
import re

root = Path(r"V:\___VAC\__K\__CODE\_PY\_SAIPENVIEW")
board = root / ".saipen" / "BOARD.md"
text = board.read_text(encoding="utf-8")

# Pattern to match: | verify: <rest of the line>
# We want to replace it with: | verify: PASS -- <rest of the line>
# But only if it doesn't already start with PASS --

def fix_verify_line(line):
    if "| verify:" in line:
        # check if it's already PASS --
        if "PASS --" not in line:
            return line.replace("| verify:", "| verify: PASS --")
    return line

lines = text.splitlines()
new_lines = []
for line in lines:
    new_lines.append(fix_verify_line(line))

board.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print("fixed all verify lines with PASS --")
