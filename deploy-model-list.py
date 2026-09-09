import copy
import http.client
import json
import pathlib
import socket
import subprocess
import sys
import urllib.request

BASE = 'sub2api-v022-version-badge-20260908'
NAME = 'sub2api-v022-scheduler-refinement-20260908'
IMAGE = 'sub2api:custom-v0.2.2-buaga-scheduler-refinement-20260908'
PORT = 18145
SOURCE = pathlib.Path('/home/serveradmin/candidates/buaga-v022-scheduler-refinement-20260908')
BASE_SOURCE = pathlib.Path('/home/serveradmin/candidates/buaga-v022-version-badge-20260908')

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
    assert pathlib.Path('/home/serveradmin/candidates/buaga-current-custom').resolve() == BASE_SOURCE
    assert baseline['State']['Health']['Status'] == 'healthy'
    assert 'GATEWAY_SCHEDULING_SKIP_STARTUP_CLEANUP=true' in baseline['Config']['Env']
    payload = copy.deepcopy(baseline['Config'])
    payload['Image'] = IMAGE
    payload.pop('Hostname', None)
    payload['Labels'] = {**payload.get('Labels', {}), 'buaga.release': 'v0.2.2-scheduler-refinement-20260908', 'buaga.rollback': BASE}
    payload['HostConfig'] = copy.deepcopy(baseline['HostConfig'])
    payload['HostConfig']['PortBindings'] = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(PORT)}]}
    docker('POST', f'/containers/create?name={NAME}', payload)
    docker('POST', f'/containers/{NAME}/start')
    print('Candidate started on loopback port', PORT)
else:
    candidate = docker('GET', f'/containers/{NAME}/json')
    assert candidate['State']['Health']['Status'] == 'healthy'
    assert candidate['Config']['Env'] == baseline['Config']['Env']
    assert candidate['HostConfig']['Binds'] == baseline['HostConfig']['Binds']
    assert candidate['HostConfig']['NetworkMode'] == baseline['HostConfig']['NetworkMode']
    manifest = json.loads((SOURCE / 'backend/internal/web/dist/scheduler-overlay-manifest.json').read_text())
    def asset_hashes(container):
        output = subprocess.check_output(['docker', 'exec', container, 'find', '/app/.buaga-release/assets', '-maxdepth', '1', '-type', 'f', '-exec', 'sha256sum', '{}', '+']).decode()
        return dict((pathlib.Path(line.split('  ', 1)[1]).name, line.split('  ', 1)[0]) for line in output.splitlines())
    assert asset_hashes(BASE) == asset_hashes(NAME), 'Approved frontend asset changed unexpectedly'
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/login', timeout=15) as response:
        assert b'/assets/scheduler-refinement-r1/' in response.read()
    before_settings = json.load(urllib.request.urlopen('http://127.0.0.1:18140/api/v1/settings/public', timeout=15))
    after_settings = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/v1/settings/public', timeout=15))
    assert before_settings == after_settings, 'Public settings drift'
    key = subprocess.check_output(['docker','exec','sub2api-return-postgres','psql','-U','sub2api','-d','sub2api','-Atc',"select value from settings where key='admin_api_key'"]).decode().strip()
    try:
        key = json.loads(key)
    except ValueError:
        pass
    results = []
    request = urllib.request.Request(f'http://127.0.0.1:{PORT}/api/v1/admin/ops/scheduler', headers={'x-api-key': key})
    with urllib.request.urlopen(request, timeout=15) as response:
        snapshot = json.load(response)['data']
    assert isinstance(snapshot['model_cooldowns'], list)
    version = subprocess.check_output(['docker','exec',NAME,'/app/sub2api','--version'], stderr=subprocess.STDOUT).decode()
    assert 'buaga-custom-v0.2.2-scheduler-refinement-20260908' in version
    print(json.dumps({'healthy': True, 'configuration_preserved': True, 'approved_assets_preserved': len(manifest['originals']), 'scheduler_api': True}))
