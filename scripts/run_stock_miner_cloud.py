"""Run the existing validated publisher in a fresh checkout on a fixed-IP VPS."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    missing = [name for name in ("KIWOOM_APP_KEY", "KIWOOM_SECRET_KEY", "DART_API_KEY")
               if not os.environ.get(name, "").strip()]
    if missing:
        print("서버 환경변수 필요: " + ", ".join(missing), file=sys.stderr)
        raise SystemExit(78)
    # Fresh checkout means failed output or an interrupted rebase cannot poison
    # the next scheduled run. Credentials stay in the service environment.
    env = dict(os.environ, STOCK_MINER_AUTH="env", GIT_TERMINAL_PROMPT="0", PYTHONUNBUFFERED="1")
    remote = "git@github.com:gptjyp-ops/JYP-COWRK.git"
    with TemporaryDirectory(prefix="stock-miner-cloud-") as temp:
        repo = Path(temp) / "repo"
        subprocess.run(["git", "clone", "--quiet", "--single-branch", "--branch", "main",
                        remote, str(repo)], check=True, env=env)
        subprocess.run([sys.executable, "scripts/publish_stock_miner.py"],
                       cwd=repo, check=True, env=env)


if __name__ == "__main__":
    main()
