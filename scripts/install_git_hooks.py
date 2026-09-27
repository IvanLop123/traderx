#!/usr/bin/env python3
"""Install the repo's local credential checks; no remote operations."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
for hook in (root/'.githooks').iterdir():hook.chmod(0o755)
subprocess.run(['git','-C',str(root),'config','core.hooksPath','.githooks'],check=True)
print('Local pre-commit and pre-push credential checks installed.')
