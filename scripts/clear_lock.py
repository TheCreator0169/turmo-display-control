import os
from pathlib import Path
p = Path(os.environ.get("APPDATA", "")) / "TURMO" / "monitor.lock"
try:
    p.unlink()
    print("removed")
except Exception as e:
    print("failed", e)