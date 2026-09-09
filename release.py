import copy, fcntl, hashlib, json, pathlib, shutil, subprocess, sys, urllib.request

BASE = 'sub2api-v023-monitor-sort-fix-r2-20260908'
NAME = 'sub2api-v023-long-notice-20260908'
IMAGE = 'sub2api:custom-v0.2.3-buaga-long-notice-20260908'
PORT = 18149

def inspect(name):
    return json.loads(subprocess.check_output(['docker','inspect',name]))[0]

def sql(query):
    return subprocess.check_output(['docker','exec','sub2api-return-postgres','psql','-U','sub2api','-d','sub2api','-Atc',query]).decode().strip()

def request(port,path,key=None,data=None):
    headers = {'x-api-key':key} if key else {}
    if data is not None: headers['Content-Type']='application/json'
    req=urllib.request.Request(f'http://127.0.0.1:{port}/api/v1/{path}',headers=headers,data=None if data is None else json.dumps(data).encode(),method='GET' if data is None else 'PUT')
    with urllib.request.urlopen(req,timeout=30) as response:
        return json.load(response)['data']

def verify():
    base, candidate=inspect(BASE),inspect(NAME)
    assert candidate['State']['Health']['Status']=='healthy'
    assert sorted(base['Config']['Env'])==sorted(candidate['Config']['Env'])
    for field in ['Binds','NetworkMode']:
        assert base['HostConfig'][field]==candidate['HostConfig'][field]
    hashes=[]
    for container in [BASE,NAME]:
        hashes.append(subprocess.check_output(['docker','exec',container,'sh','-c','cd /app/.buaga-release && find . -type f -exec sha256sum {} \\; | sort']))
    assert hashes[0]==hashes[1], 'Frontend mismatch: do not bypass'
    key=sql("SELECT value FROM settings WHERE key='admin_api_key'")
    if key.startswith('"'): key=json.loads(key)
    saved=sql("SELECT value FROM settings WHERE key='long_notice_content'")
    assert saved
    public=request(PORT,'settings/public')
    assert public['long_notice_content']==saved
    admin=request(PORT,'admin/settings',key)
    assert admin['long_notice_content']==saved
    monitors=request(PORT,'admin/channel-monitors/all',key)
    assert len(monitors)==int(sql('SELECT count(*) FROM channel_monitors'))
    print(json.dumps({'health':'healthy','notice_matches_database':True,'notice_characters':len(saved),'admin_notice_matches':True,'frontend_identical':True,'monitors':len(monitors)}))

mode=sys.argv[1]
if mode=='create':
    import http.client, socket
    class Connection(http.client.HTTPConnection):
        def connect(self):
            self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.sock.connect('/var/run/docker.sock')
    base=inspect(BASE)
    payload=copy.deepcopy(base['Config']); payload['Image']=IMAGE; payload.pop('Hostname',None)
    payload['HostConfig']=copy.deepcopy(base['HostConfig'])
    payload['HostConfig']['PortBindings']={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':str(PORT)}]}
    for path,body in [(f'/containers/create?name={NAME}',payload),(f'/containers/{NAME}/start',None)]:
        conn=Connection('localhost'); conn.request('POST',path,None if body is None else json.dumps(body),{'Content-Type':'application/json'})
        response=conn.getresponse(); assert response.status<300, response.status; response.read(); conn.close()
elif mode=='verify': verify()
elif mode=='switch':
    with open('/home/serveradmin/.buaga-deploy.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        verify()
        config=pathlib.Path('/etc/nginx/conf.d/sub2api-global.conf'); before=config.read_text()
        old='    server 127.0.0.1:18148;'; new='    server 127.0.0.1:18149;'
        assert before.count(old)==1 and new not in before, 'Active release changed'
        backup=pathlib.Path('/home/serveradmin/.codex-backups/long-notice-20260908'); backup.mkdir(exist_ok=False)
        shutil.copy2(config,backup/config.name)
        try:
            config.write_text(before.replace(old,new,1))
            subprocess.run(['nginx','-t'],check=True)
            subprocess.run(['systemctl','reload','nginx'],check=True)
            verify()
        except Exception:
            shutil.copy2(backup/config.name,config)
            subprocess.run(['nginx','-t'],check=True)
            subprocess.run(['systemctl','reload','nginx'],check=True)
            raise
        print('switched; prior container retained')
