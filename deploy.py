import datetime, fcntl, hashlib, json, os, re, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

OLD='sub2api-v023-announcement-close-20260909'
NEW='sub2api-v023-announcement-status-20260909'
IMAGE='sub2api:custom-v023-announcement-status-20260909'
SOURCE=Path('/home/serveradmin/candidates/buaga-v023-announcement-status-20260909')
POINTER=SOURCE.parent/'buaga-current-custom'
CONF=Path('/etc/nginx/conf.d/sub2api-global.conf')
BACKUP=Path('/home/serveradmin/.codex-backups/announcement-status-20260909')
IDS='356,361,377,441,448,464'

def run(args): return subprocess.check_output(args,text=True).strip()
def inspect(name): return json.loads(run(['docker','inspect',name]))[0]
def sql(query): return run(['docker','exec','sub2api-return-postgres','psql','-U','sub2api','-d','sub2api','-Atc',query])
def db_identity():
    data=sql(f"SELECT json_agg(x ORDER BY id) FROM (SELECT id,credentials,extra-'upstream_model_metadata'-'upstream_billing_probe' AS extra FROM accounts WHERE id IN ({IDS})) x")
    return hashlib.sha256(data.encode()).hexdigest()

def announcement_identity():
    data=sql("SELECT json_agg(x ORDER BY id) FROM (SELECT * FROM announcements) x")
    return hashlib.sha256(data.encode()).hexdigest()

def get(port,path,admin=False):
    headers={'Host':'buaga.dpdns.org'}
    if admin: headers['x-api-key']=sql("SELECT value FROM settings WHERE key='admin_api_key'")
    with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}'+path,headers=headers),timeout=25) as response:
        return response.read(),response.headers.get('Content-Type','')

def checks():
    assert inspect(NEW)['State']['Running']
    assert json.loads(get(18159,'/health')[0])['status']=='ok'
    for path,admin in [('/api/v1/settings/public',False),('/api/v1/admin/settings',True),('/api/v1/admin/channel-monitors/all',True)]:
        a=json.loads(get(18158,path,admin)[0]);b=json.loads(get(18159,path,admin)[0])
        if path.endswith('/all'):
            a=[(x['id'],x.get('sort_order')) for x in a['data']]
            b=[(x['id'],x.get('sort_order')) for x in b['data']]
        assert a==b,'Existing settings or channel order differ: '+path
    page=get(18159,'/login')[0].decode()
    assert '<div id="app"' in page
    assets=re.findall(r'(?:src|href)="(/assets/[^"?]+)',page)
    assert assets
    for asset in assets:
        data,kind=get(18159,asset);assert data and 'text/html' not in kind
    assert db_identity()==(BACKUP/'account-identity.sha256').read_text(),'Account configuration changed during repair'
    assert announcement_identity()==(BACKUP/'announcement-identity.sha256').read_text(),'Announcement configuration changed during release'
    print('PASS health, public/admin settings, long notice, channel order, UI entry assets, account credentials/mappings',flush=True)

lock=open('/home/serveradmin/.codex-catalog-release.lock','w')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
mode=sys.argv[1]
if mode=='prepare':
    assert 'server 127.0.0.1:18158;' in CONF.read_text(),'Active release changed'
    old=inspect(OLD)
    assert old['State']['Running']
    assert 'GATEWAY_SCHEDULING_SKIP_STARTUP_CLEANUP=true' in old['Config']['Env']
    assert not run(['docker','ps','-aqf','name=^'+NEW+'$']),'Candidate already exists'
    assert not BACKUP.exists(),'Backup already exists; inspect before retrying'
    BACKUP.mkdir(mode=0o700,parents=True)
    (BACKUP/'nginx.conf').write_bytes(CONF.read_bytes())
    (BACKUP/'source-pointer').write_text(str(POINTER.resolve()))
    (BACKUP/'account-identity.sha256').write_text(db_identity())
    (BACKUP/'announcement-identity.sha256').write_text(announcement_identity())
    snapshot=sql(f"SELECT json_agg(x) FROM (SELECT id,extra->'upstream_model_metadata' AS metadata FROM accounts WHERE id IN ({IDS})) x")
    (BACKUP/'capabilities.json').write_text(snapshot)
    args=['docker','run','-d','--name',NEW,'--restart','unless-stopped','--log-driver','json-file','--log-opt','max-size=50m','--log-opt','max-file=5','--network',old['HostConfig']['NetworkMode'],'-p','127.0.0.1:18159:8080']
    for mount in old['Mounts']:
        assert mount['Type'] in ('bind','volume')
        src=mount['Source'] if mount['Type']=='bind' else mount['Name']
        args+=['--mount',f'type={mount["Type"]},src={src},dst={mount["Destination"]}'+('' if mount['RW'] else ',readonly')]
    with tempfile.NamedTemporaryFile(mode='w',prefix='catalog-env-') as env:
        assert all('\n' not in value for value in old['Config']['Env'])
        env.write('\n'.join(old['Config']['Env'])+'\n');env.flush()
        run(args+['--env-file',env.name,IMAGE])
    for i in range(30):
        try:
            get(18159,'/health');break
        except Exception: time.sleep(1)
    checks()
elif mode=='check': checks()
elif mode=='switch':
    checks()
    original=(BACKUP/'nginx.conf').read_text()
    assert CONF.read_text()==original,'Nginx changed since preparation; do not overwrite another release'
    assert str(POINTER.resolve())==(BACKUP/'source-pointer').read_text(),'Source pointer changed'
    assert original.count('server 127.0.0.1:18158;')==1
    try:
        CONF.write_text(original.replace('server 127.0.0.1:18158;','server 127.0.0.1:18159;'))
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
        checks()
    except Exception:
        CONF.write_text(original)
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
        raise
    temp=POINTER.with_name('buaga-current-custom.announcement-next')
    temp.symlink_to(SOURCE);temp.replace(POINTER)
    release={'version':'0.2.3','release':NEW,'image':IMAGE,'image_id':inspect(NEW)['Image'],'container':NEW,'upstream':'127.0.0.1:18159','remote_source':str(SOURCE),'default_source':str(POINTER),'local_source':'/Volumes/WIN-SSD/服务器/.codex-work/announcement-status-20260909/source','verification_date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rollback':{'container':OLD,'upstream':'127.0.0.1:18158','backup':str(BACKUP)},'scope':'Capability sync across relay protocols, preview classification, cache freshness and actionable missing-model warnings; preserve web performance and image preview customizations'}
    release['scope']='Always show announcement footer status: actionable mark-all-read when unread items exist, disabled no-unread status otherwise. Preserve popup batch dismissal and all previous custom features.'
    (SOURCE/'CURRENT_RELEASE.json').write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
    print('SWITCHED 18158 -> 18159; previous container retained for in-flight requests and rollback',flush=True)
else: raise SystemExit('Unknown mode')
