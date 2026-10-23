"""Preserve the stuck checkout, collect in a fresh one, then reconnect the task.

Run with the same Windows user and existing Kiwoom virtualenv. Never resets,
stashes, aborts, removes or pushes changes from the original checkout.
"""
from __future__ import annotations

import base64
import getpass
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REMOTE = 'https://github.com/gptjyp-ops/JYP-COWRK.git'
TASK = 'Stock Miner Daily Upload'


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def powershell(script, *, capture=False):
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                           '-EncodedCommand', encoded], check=True,
                          stdout=subprocess.PIPE if capture else None,
                          text=True, encoding='utf-8', errors='replace')


def restore_user_dart_key():
    # Scheduled tasks need a persistent user-level key, not just the open shell.
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            value, _ = winreg.QueryValueEx(key, 'DART_API_KEY')
    except FileNotFoundError:
        value = ''
    value = str(value).strip()
    if not value:
        value = os.environ.get('DART_API_KEY', '').strip()
        if not value:
            print('DART key is missing. Enter it only in this PC window, not in chat.', flush=True)
            value = getpass.getpass('DART_API_KEY (hidden): ').strip()
        if not value:
            raise RuntimeError('DART_API_KEY is required. Task was not changed.')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            winreg.SetValueEx(key, 'DART_API_KEY', 0, winreg.REG_SZ, value)
    os.environ['DART_API_KEY'] = value


def reconnect_task(repo):
    script = f"""
$ErrorActionPreference = 'Stop'
$taskName = {ps_quote(TASK)}
$repo = {ps_quote(repo)}
$python = {ps_quote(sys.executable)}
$runner = Join-Path $repo 'scripts/run_stock_miner_logged.py'
$action = New-ScheduledTaskAction -Execute $python -Argument ('-u "' + $runner + '"') -WorkingDirectory $repo
$old = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($old) {{
    Export-ScheduledTask -TaskName $taskName | Set-Content -Encoding UTF8 (Join-Path $repo 'stock-miner-logs/previous-task.xml')
    Set-ScheduledTask -TaskName $taskName -Action $action | Out-Null
}} else {{
    $triggers = @(
        (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '09:20'),
        (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '14:20'),
        (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '16:30')
    )
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal | Out-Null
}}
$updated = Get-ScheduledTask -TaskName $taskName
if ($updated.Actions.Execute -ne $python -or $updated.Actions.WorkingDirectory -ne $repo) {{ throw 'Task action verification failed' }}
Enable-ScheduledTask -TaskName $taskName | Out-Null
Get-ScheduledTaskInfo -TaskName $taskName | Format-List LastRunTime,LastTaskResult,NextRunTime
"""
    powershell(script)


def main():
    if sys.platform != 'win32':
        raise RuntimeError('Run this on the Kiwoom registered Windows PC.')
    sys.stdout.reconfigure(errors='replace')
    # Refuse a second collection if the scheduled collector is still running.
    state = powershell("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                       f"$t=Get-ScheduledTask -TaskName {ps_quote(TASK)} -ErrorAction SilentlyContinue; "
                       "if($t){Write-Output $t.State}", capture=True).stdout.lstrip('\ufeff').strip()
    if state == 'Running':
        raise RuntimeError('The scheduled collector is still running. Wait for it to finish before repairing.')
    restore_user_dart_key()
    print('[1/5] Checking the existing Python/Kiwoom environment...', flush=True)
    subprocess.run([sys.executable, '-c', 'from kiwoom import get_client, KiwoomError; import requests; print("Python imports OK")'], check=True)
    desktop = Path(os.environ['USERPROFILE']) / 'Desktop'
    repo = Path(tempfile.mkdtemp(prefix='JYP-COWRK-Recovery-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-', dir=desktop))
    print('[2/5] Creating a clean checkout: ' + str(repo), flush=True)
    print('The original JYP-COWRK folder and its unfinished Git operation are preserved.', flush=True)
    subprocess.run(['git', 'clone', '--depth', '1', '--single-branch', '--branch', 'main', REMOTE, str(repo)], check=True)
    env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
    # Explicitly keep the PC keyring authentication, even if a shell was used to test cloud mode.
    env.pop('STOCK_MINER_AUTH', None)
    print('[3/5] Collecting Kiwoom + DART and publishing. Keep this window open.', flush=True)
    subprocess.run([sys.executable, '-u', 'scripts/run_stock_miner_logged.py'], cwd=repo, env=env, check=True)
    print('[4/5] Verifying the data actually reached GitHub...', flush=True)
    expected = json.loads((repo / 'data/stock-miner-v4-meta.json').read_text(encoding='utf-8'))
    subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=repo, check=True)
    result = subprocess.run(['git', 'show', 'FETCH_HEAD:data/stock-miner-v4-meta.json'], cwd=repo,
                            check=True, stdout=subprocess.PIPE, encoding='utf-8')
    published = json.loads(result.stdout)
    for field in ('generated_at', 'generated_at_dart', 'count'):
        if published.get(field) != expected.get(field):
            raise RuntimeError('Published metadata does not match this collection. Task was not changed.')
    print('[5/5] Connecting the scheduled task to the verified checkout...', flush=True)
    reconnect_task(repo)
    print('RECOVERY COMPLETE: ' + str(expected['generated_at']) + ' / ' + str(expected['count']) + ' stocks', flush=True)
    print('Original folder preserved. New scheduled folder: ' + str(repo), flush=True)
    print('Check the updated timestamp on https://gptjyp-ops.github.io/JYP-COWRK/stock-miner.html', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print('RECOVERY STOPPED: ' + str(error), file=sys.stderr, flush=True)
        print('Keep the final error lines. The original checkout was not changed.', file=sys.stderr)
        raise SystemExit(1)
