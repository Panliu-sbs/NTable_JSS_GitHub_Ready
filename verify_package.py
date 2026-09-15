from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd, cwd):
    print("+", " ".join(cmd), f"(cwd={cwd})")
    env = os.environ.copy()
    return subprocess.run(cmd, cwd=str(cwd), env=env, check=True).returncode


def main():
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], ROOT / "core_rq3")
    run([sys.executable, "test_reconstruction.py"], ROOT / "baselines" / "ast_ep_ht_ep")
    print("\nCore N-Table/Pratt tests and AST-EP/HT-EP reconstruction checks passed.")
    print("RQ3 timing and figure generation are intentionally not run by this quick verifier.")


if __name__ == "__main__":
    main()
