"""Stream collector output to both the console and a UTF-8 log on Windows."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_logged(repo: Path, command: list[str]) -> int:
    logs = repo / 'stock-miner-logs'
    logs.mkdir(exist_ok=True)
    path = logs / ('upload-' + datetime.now().strftime('%Y-%m-%d-%H%M%S-%f') + '.log')
    env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
    if sys.platform == 'win32':
        env.pop('STOCK_MINER_AUTH', None)
    print('Log: ' + str(path), flush=True)
    with path.open('w', encoding='utf-8') as log:
        def emit(line):
            log.write(line)
            log.flush()
            sys.stdout.write(line)
            sys.stdout.flush()
        emit('START ' + datetime.now().isoformat(timespec='seconds') + '\n')
        try:
            with subprocess.Popen(command, cwd=repo, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                  errors='replace', bufsize=1) as process:
                for line in process.stdout:
                    emit(line)
                code = process.wait()
        except Exception as error:
            emit('LAUNCH FAILED: ' + type(error).__name__ + '\n')
            raise
        emit('END exit_code=' + str(code) + '\n')
    return code


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    repo = Path(__file__).resolve().parents[1]
    return run_logged(repo, [sys.executable, '-u', 'scripts/publish_stock_miner.py'])


if __name__ == '__main__':
    raise SystemExit(main())
