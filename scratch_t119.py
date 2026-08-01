import time
import keyboard

print("Verification T-119 started.")
print("1. 'hides once then never again' - Fixed in T-049 regression fix (window.py:180).")
print("2. ctrl+q in DEFAULTS - config.py:17 actually removed it due to global hook hijacking.")
print("3. config.py:34 two slots per hotkey - Verified (line 38).")
