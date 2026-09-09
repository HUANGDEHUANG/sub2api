import collections, json, subprocess, urllib.request, urllib.error
from pathlib import Path

NAME = 'sub2api-v023-announcement-status-20260909'
def run(args): return subprocess.check_output(args, text=True).strip()
def sql(q): return run(['docker','exec','sub2api-return-postgres','psql','-U','sub2api','-d','sub2api','-Atc',q])
key = sql("SELECT value FROM settings WHERE key='admin_api_key'")
results = []
for path, auth, expected in [('/health',False,200),('/api/v1/admin/ops/scheduler',True,200),('/api/v1/admin/system/version',True,200),('/api/v1/admin/accounts/464/models',True,200),('/api/v1/admin/usage?page=1&page_size=5',True,200),('/api/v1/admin/usage/0/images/0',True,404),('/api/v1/admin/usage/0/images/0',False,401)]:
    headers = {'Host':'buaga.dpdns.org'}
    if auth: headers['x-api-key'] = key
    try:
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18159'+path,headers=headers),timeout=25) as r:
            status = r.status
            data = json.load(r)
    except urllib.error.HTTPError as e: status = e.code
    assert status == expected, (path,status,expected)
    results.append({'path':path,'auth':auth,'status':status})
item = json.loads(run(['docker','inspect',NAME]))[0]
assert item['HostConfig']['LogConfig'] == {'Type':'json-file','Config':{'max-size':'50m','max-file':'5'}}
assert not item['State']['OOMKilled'] and item['RestartCount'] == 0
logs = subprocess.run(['docker','logs','--since','3m',NAME],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True).stdout
counts = collections.Counter()
balance_ids = set()
for line in logs.splitlines():
    try: e=json.loads(line)
    except ValueError: continue
    msg=e.get('msg','')
    if 'completed_at' in e and 'method' in e: counts['HTTP_'+str(e.get('status_code'))]+=1
    if msg.startswith('Gemini account') and 'context canceled' in msg: counts['gemini_canceled_retry']+=1
    if msg == 'upstream_balance_cooldown':
        counts['balance_cooldown']+=1
        if isinstance(e.get('account_id'),int): balance_ids.add(e['account_id'])
    if e.get('level','').upper() in ('PANIC','FATAL'): counts['fatal_or_panic']+=1
assert counts['fatal_or_panic']==0
print(json.dumps({'checks':results,'health':item['State'].get('Health',{}).get('Status'),'log_rotation':item['HostConfig']['LogConfig'],'recent_events':counts}))
print('BALANCE_STATE '+sql("SELECT json_agg(x) FROM (SELECT id,temp_unschedulable_until FROM accounts WHERE id IN (334,388)) x"))
if balance_ids:
    ids = ','.join(str(x) for x in sorted(balance_ids))
    print('OBSERVED_COOLDOWNS '+sql(f"SELECT json_agg(x) FROM (SELECT id,temp_unschedulable_until FROM accounts WHERE id IN ({ids})) x"))
