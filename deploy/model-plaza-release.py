"""Scoped, reversible model-plaza release. Run with sudo on the production host."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request

ROOT = Path('/home/serveradmin/candidates/buaga-v022-model-plaza-20260908')
OLD_ROOT = Path('/home/serveradmin/candidates/buaga-v022-model-list-fix-20260908')
OLD = 'sub2api-v022-model-list-fix-20260908'
NEW = 'sub2api-v022-model-plaza-20260908'
IMAGE = 'sub2api:custom-v0.2.2-buaga-model-plaza-20260908'
NGINX = Path('/etc/nginx/conf.d/sub2api-global.conf')
BACKUP = Path('/opt/sub2api-return/backup/model-plaza-20260908')
KEYS = ['model_plaza_enabled', 'model_plaza_require_auth', 'model_plaza_description', 'model_plaza_catalog']
TABLES = ['groups', 'channels', 'channel_groups', 'channel_model_pricing', 'channel_pricing_intervals', 'channel_account_stats_pricing_rules']

def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def output(args):
    return subprocess.check_output(args, text=True)

def sql(query):
    return run(['docker', 'exec', '-i', 'sub2api-return-postgres', 'psql', '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-U', 'sub2api', '-d', 'sub2api'], input=query, text=True, capture_output=True).stdout.strip()

def literal(value):
    return "'" + value.replace("'", "''") + "'"

def fingerprints():
    return {table: sql(f"SELECT md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.id)::text,'')) FROM {table} t;") for table in TABLES}

def file_hashes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file() and not p.name.startswith('._')}

def healthy(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=10) as response:
        assert response.status == 200

def atomic_nginx(content):
    temp = NGINX.with_suffix('.plaza-tmp')
    temp.write_text(content)
    os.chmod(temp, NGINX.stat().st_mode & 0o777)
    os.replace(temp, NGINX)
    run(['nginx', '-t'], capture_output=True)
    run(['nginx', '-s', 'reload'], capture_output=True)

def prepare():
    assert 'server 127.0.0.1:18137;' in NGINX.read_text(), 'Production moved; inspect before deploying'
    assert file_hashes(ROOT / 'backend/migrations') == file_hashes(OLD_ROOT / 'backend/migrations'), 'Migration drift'
    assert file_hashes(ROOT / 'backend/internal/web/dist') == file_hashes(OLD_ROOT / 'backend/internal/web/dist'), 'Custom UI drift'
    BACKUP.mkdir(mode=0o700)
    (BACKUP / 'nginx.conf').write_bytes(NGINX.read_bytes())
    settings = sql('SELECT coalesce(jsonb_object_agg(key,value),\'{}\'::jsonb) FROM settings WHERE key IN (' + ','.join(map(literal, KEYS)) + ');')
    (BACKUP / 'settings.json').write_text(settings)
    assert json.loads(settings).get('model_plaza_enabled') == 'false'
    (BACKUP / 'billing-fingerprints.json').write_text(json.dumps(fingerprints(), indent=2))
    with (BACKUP / 'pricing-config.dump').open('wb') as dump:
        run(['docker', 'exec', 'sub2api-return-postgres', 'pg_dump', '-U', 'sub2api', '-d', 'sub2api', '-Fc'] + [flag for table in TABLES for flag in ('-t', table)], stdout=dump)
    print('Prepared private backup; migrations and custom frontend unchanged.')

def start():
    assert BACKUP.exists()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 18138))
    old = json.loads(output(['docker', 'inspect', OLD]))[0]
    assert list(old['NetworkSettings']['Networks']) == ['sub2api-return-network']
    args = ['docker', 'run', '-d', '--name', NEW, '--restart', 'unless-stopped', '--network', 'sub2api-return-network', '-p', '127.0.0.1:18138:8080', '--label', 'buaga.release=v0.2.2-model-plaza-20260908', '--label', 'buaga.rollback=' + OLD]
    for env in old['Config']['Env']:
        args.extend(['--env', env])
    for mount in old['Mounts']:
        assert mount['Type'] == 'bind'
        args.extend(['--mount', 'type=bind,src=' + mount['Source'] + ',dst=' + mount['Destination'] + ('' if mount['RW'] else ',readonly')])
    args.extend([IMAGE] + old['Config']['Cmd'])
    run(args, capture_output=True)
    print('Candidate started on 127.0.0.1:18138; production unchanged.')

def verify():
    healthy(18138)
    with urllib.request.urlopen('http://127.0.0.1:18138/api/v1/model-plaza', timeout=30) as response:
        data = json.load(response)['data']
    catalog = json.loads((ROOT / 'deploy/model-plaza-catalog.json').read_text())
    assert sorted(g['id'] for g in data['groups']) == sorted(g['group_id'] for g in catalog), 'Wrong storefront group scope'
    groups = {g['id']: g for g in data['groups']}
    expected_rates = {149: .068, 5: .088, 88: .15, 45: .2, 26: .3, 116: 1, 128: .3, 95: .1, 153: .45, 151: .58, 144: .75, 120: 1, 65: .5}
    for gid, rate in expected_rates.items():
        assert abs(groups[gid]['rate_multiplier'] - rate) < 1e-12
        assert groups[gid]['models'], f'Empty group {gid}'
    for model in groups[116]['models']:
        assert model['pricing']['billing_mode'] == 'image'
        tiers = {iv['tier_label']: iv['per_request_price'] for iv in model['pricing']['intervals']}
        assert tiers == {'1K': .08, '2K': .12, '4K': .2}, tiers
    sonnet = next(m for m in groups[95]['models'] if m['name'] == 'claude-sonnet-4-6')
    assert abs(sonnet['pricing']['input_price'] * .1 * 1e6 - .3) < 1e-9
    gemini = next(m for m in groups[128]['models'] if m['name'] == 'gemini-2.5-flash')
    assert abs(gemini['pricing']['input_price'] * .3 * 1e6 - .018) < 1e-9
    before = json.loads((BACKUP / 'billing-fingerprints.json').read_text())
    assert before == fingerprints(), 'Pricing configuration changed; investigate before accepting release'
    (BACKUP / 'verified-plaza.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps({'groups': len(groups), 'models_by_group': {g['name']: len(g['models']) for g in data['groups']}, 'billing_configuration_unchanged': True}, ensure_ascii=False))

def restore_settings():
    previous = json.loads((BACKUP / 'settings.json').read_text())
    statements = ['BEGIN;']
    for key in KEYS:
        if key in previous:
            statements.append(f'INSERT INTO settings(key,value) VALUES ({literal(key)},{literal(previous[key])}) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;')
        elif key == 'model_plaza_catalog':
            statements.append(f'DELETE FROM settings WHERE key={literal(key)};')
    statements.append('COMMIT;')
    sql('\n'.join(statements))

def activate():
    healthy(18138)
    current = NGINX.read_text()
    assert current == (BACKUP / 'nginx.conf').read_text(), 'Nginx changed since prepare'
    assert fingerprints() == json.loads((BACKUP / 'billing-fingerprints.json').read_text()), 'Pricing changed since prepare'
    catalog = json.loads((ROOT / 'deploy/model-plaza-catalog.json').read_text())
    description = '实付价格按当前分组的实际计费规则计算。Token 价格单位为美元 / 百万 Token，生图按张计费。分组倍率作用于现有计费基准，不一定等于实付价与官方参考价的比值；Gemini 等渠道保留当前自定义基准价。'
    try:
        atomic_nginx(current.replace('server 127.0.0.1:18137;', 'server 127.0.0.1:18138;', 1))
        healthy(18138)
        values = {'model_plaza_catalog': json.dumps(catalog, ensure_ascii=False), 'model_plaza_description': description, 'model_plaza_enabled': 'true'}
        sql('BEGIN;\n' + '\n'.join(f'INSERT INTO settings(key,value) VALUES ({literal(k)},{literal(v)}) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;' for k, v in values.items()) + '\nCOMMIT;')
        verify()
    except Exception:
        restore_settings()
        atomic_nginx(current)
        raise
    pointer = ROOT.parent / 'buaga-current-custom'
    assert pointer.resolve() == OLD_ROOT
    temp_pointer = ROOT.parent / 'buaga-current-custom.plaza-tmp'
    temp_pointer.symlink_to(ROOT)
    os.replace(temp_pointer, pointer)
    print('Activated with graceful Nginx reload; previous container retained for rollback.')

if __name__ == '__main__':
    assert os.geteuid() == 0, 'Run with sudo'
    actions = {'prepare': prepare, 'start': start, 'activate': activate, 'verify': verify}
    actions[sys.argv[1]]()
