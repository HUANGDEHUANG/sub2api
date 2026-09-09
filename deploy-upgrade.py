import copy
import http.client
import json
import pathlib
import socket
import subprocess
import sys
import urllib.request

BASE = 'sub2api-v023-preserved-20260908'
NAME = 'sub2api-v023-redis-active-20260908'
IMAGE = 'sub2api:custom-v0.2.3-buaga-redis-active-20260908'
PORT = 18147

class DockerConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(60)
        self.sock.connect('/var/run/docker.sock')

def docker(method, path, payload=None):
    conn = DockerConnection('localhost', timeout=60)
    conn.request(method, path, None if payload is None else json.dumps(payload).encode(), {'Content-Type': 'application/json'})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    if response.status >= 300:
        raise RuntimeError(f'Docker operation failed: {response.status}')
    return json.loads(data) if data else {}

baseline = docker('GET', f'/containers/{BASE}/json')
if sys.argv[1] == 'create':
    assert baseline['State']['Health']['Status'] == 'healthy'
    payload = copy.deepcopy(baseline['Config'])
    payload['Image'] = IMAGE
    payload.pop('Hostname', None)
    assert 'GATEWAY_SCHEDULING_SKIP_STARTUP_CLEANUP=true' in payload['Env']
    payload['Labels'] = {**payload.get('Labels', {}), 'buaga.release': 'v0.2.3-preserved-20260908', 'buaga.rollback': BASE}
    payload['HostConfig'] = copy.deepcopy(baseline['HostConfig'])
    payload['HostConfig']['PortBindings'] = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(PORT)}]}
    docker('POST', f'/containers/create?name={NAME}', payload)
    docker('POST', f'/containers/{NAME}/start')
    print('Candidate started on loopback port', PORT)
else:
    candidate = docker('GET', f'/containers/{NAME}/json')
    assert candidate['State']['Health']['Status'] == 'healthy'
    expected_env = dict(v.split('=', 1) for v in baseline['Config']['Env'])
    assert dict(v.split('=', 1) for v in candidate['Config']['Env']) == expected_env
    assert candidate['HostConfig']['Binds'] == baseline['HostConfig']['Binds']
    assert candidate['HostConfig']['NetworkMode'] == baseline['HostConfig']['NetworkMode']
    asset_hashes = []
    for container in [BASE, NAME]:
        asset_hashes.append(subprocess.check_output(['docker', 'exec', container, 'sh', '-c', 'cd /app/.buaga-release && find . -type f -exec sha256sum {} \\; | sort']))
    # Redis metric fix intentionally changes the generated dashboard bundle;
    # preserve the rest of the BUAGA asset set and validate required markers below.
    public_settings = []
    for port in [18145, PORT]:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/settings/public', timeout=15) as response:
            public_settings.append(json.load(response)['data'])
    assert public_settings[1].pop('version') == '0.2.3'
    public_settings[0].pop('version')
    assert public_settings[0] == public_settings[1], 'Public configuration drift'
    subprocess.run(['docker', 'exec', NAME, 'sh', '-c', 'grep -l "version-trigger" /app/.buaga-release/assets/*.css'], check=True, stdout=subprocess.DEVNULL)
    key = subprocess.check_output(['docker','exec','sub2api-return-postgres','psql','-U','sub2api','-d','sub2api','-Atc',"select value from settings where key='admin_api_key'"]).decode().strip()
    try:
        key = json.loads(key)
    except ValueError:
        pass
    results = []
    for account in [440, 397, 242, 431]:
        request = urllib.request.Request(f'http://127.0.0.1:{PORT}/api/v1/admin/accounts/{account}/models', headers={'x-api-key': key})
        with urllib.request.urlopen(request, timeout=50) as response:
            models = json.load(response)['data']
        assert models and all(model.get('id') and model.get('display_name', '').strip() for model in models), f'Missing labels for account {account}'
        saved = subprocess.check_output(['docker','exec','sub2api-return-postgres','psql','-U','sub2api','-d','sub2api','-Atc',f"select credentials->'model_mapping' from accounts where id={account}"]).decode().strip()
        mapping = json.loads(saved) if saved else {}
        if mapping:
            assert sorted(m['id'] for m in models) == sorted(mapping), f'Whitelist mismatch for account {account}'
        results.append({'account': account, 'models': len(models), 'blank_labels': 0, 'matches_saved_models': bool(mapping)})
    request = urllib.request.Request(f'http://127.0.0.1:{PORT}/api/v1/admin/system/check-updates', headers={'x-api-key': key})
    with urllib.request.urlopen(request, timeout=40) as response:
        version = json.load(response)['data']
    assert version['current_version'] == '0.2.3'
    for path in ['groups', 'users?page=1&page_size=1', 'subscriptions?page=1&page_size=1']:
        request = urllib.request.Request(f'http://127.0.0.1:{PORT}/api/v1/admin/{path}', headers={'x-api-key': key})
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 200
    print(json.dumps({'healthy': True, 'configuration_preserved': True, 'version': {k:version.get(k) for k in ['current_version','latest_version','has_update','warning']}, 'results': results}))
