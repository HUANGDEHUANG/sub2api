import json, re, subprocess, sys
from pathlib import Path

ACTIVE = 'sub2api-v023-announcement-status-20260909'
RETIRED = {'sub2api-v023-announcement-close-20260909', 'sub2api-v023-runtime-hardening-20260909'}
BACKUP = Path('/home/serveradmin/.codex-backups/announcement-status-20260909/retired')

def run(args):
    return subprocess.check_output(args, text=True).strip()

def inspect(name):
    return json.loads(run(['docker', 'inspect', name]))[0]

def env(item):
    return dict(x.split('=', 1) for x in item['Config'].get('Env', []) if '=' in x)

assert 'server 127.0.0.1:18159;' in Path('/etc/nginx/conf.d/sub2api-global.conf').read_text()
active = inspect(ACTIVE)
assert active['State']['Health']['Status'] == 'healthy'
db = {k: v for k, v in env(active).items() if k.startswith('DATABASE_')}
assert db
nginx = subprocess.run(['nginx', '-T'], capture_output=True, text=True, check=True).stdout
results = []
for cid in run(['docker', 'ps', '-q']).splitlines():
    item = inspect(cid)
    name = item['Name'].lstrip('/')
    if name not in RETIRED:
        continue
    if not all(env(item).get(k) == v for k, v in db.items()):
        continue
    ports = [p['HostPort'] for ps in item['NetworkSettings']['Ports'].values() for p in (ps or [])]
    ips = [n['IPAddress'] for n in item['NetworkSettings']['Networks'].values() if n['IPAddress']]
    referenced = any(re.search(r':'+re.escape(p)+r'\b', nginx) for p in ports) or any(ip in nginx for ip in ips)
    connections = run(['nsenter', '-t', str(item['State']['Pid']), '-n', 'ss', '-Hnt', 'state', 'established', '( sport = :8080 )'])
    count = len(connections.splitlines()) if connections else 0
    result = {'name': name, 'nginx_referenced': referenced, 'inbound_connections': count}
    if sys.argv[1:] == ['stop'] and not referenced and count == 0:
        BACKUP.mkdir(parents=True, exist_ok=True, mode=0o700)
        snapshot = BACKUP / (name + '.json')
        if not snapshot.exists():
            snapshot.touch(mode=0o600)
            snapshot.write_text(json.dumps(item))
        # A final check prevents an old worker connection observed during inspection being interrupted.
        assert not run(['nsenter', '-t', str(item['State']['Pid']), '-n', 'ss', '-Hnt', 'state', 'established', '( sport = :8080 )'])
        run(['docker', 'stop', '--time', '120', name])
        result['stopped'] = True
    results.append(result)
print(json.dumps(results))
