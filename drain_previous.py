"""One-shot deployment drain: never interrupt established requests."""
import json, subprocess, time
from pathlib import Path

source = Path('/home/serveradmin/candidates/buaga-v023-announcement-status-20260909')
deadline = time.monotonic() + 23 * 3600
while time.monotonic() < deadline:
    # retire.py checks current deployment, health, all nginx references and
    # the container network namespace twice before it can stop anything.
    result = subprocess.run(['python3', str(source/'retire.py'), 'stop'], capture_output=True, text=True, timeout=180, check=True)
    rows = json.loads(result.stdout)
    pending = [r for r in rows if not r.get('stopped')]
    (source/'retirement-status.json').write_text(json.dumps({'checked_at':time.time(),'pending':pending,'completed':not pending},indent=2)+'\n')
    if not pending:
        print('Deployment drain complete; retired production instances stopped, images retained.',flush=True)
        break
    time.sleep(30)
else:
    raise SystemExit('Drain deadline reached; active requests were preserved. Inspect retirement-status.json.')
