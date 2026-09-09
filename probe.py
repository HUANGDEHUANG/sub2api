import json, subprocess, urllib.request, concurrent.futures

def query(sql):
    return json.loads(subprocess.check_output(['sudo','-n','docker','exec','sub2api-return-postgres','psql','-U','sub2api','-d','sub2api','-Atc',sql],text=True))

def probe(a):
    base=a['credentials']['base_url'].rstrip('/')
    url=base+('/models' if base.endswith('/v1') else '/v1/models')
    key=a['credentials']['api_key']
    headers={'Authorization':'Bearer '+key,'x-api-key':key,'anthropic-version':'2023-06-01','Accept':'application/json','User-Agent':'curl/8.0'}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=30) as r:
            b=json.load(r)
        entries=b.get('data',b.get('models',[]))
        return {'id':a['id'],'name':a['name'],'count':len(entries),'models':[{'id':m.get('id'), 'fields':list(m)} for m in entries]}
    except Exception as e:
        return {'id':a['id'],'error_type':type(e).__name__,'status':getattr(e,'code',None)}

accounts=query("SELECT json_agg(x) FROM (SELECT id,name,credentials FROM accounts WHERE id IN (448,464,441)) x")
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for result in pool.map(probe,accounts): print(json.dumps(result))
with urllib.request.urlopen(urllib.request.Request('https://models.dev/api.json',headers={'User-Agent':'curl/8.0'}),timeout=30) as r: registry=json.load(r)
for provider in ['anthropic','deepseek','zhipuai','moonshotai-cn','minimax','tencent-token-plan']:
    p=registry.get(provider,{})
    print(json.dumps({'provider':provider,'models':list(p.get('models',{}))}))
print(json.dumps({'hy4_exact_matches':[(pid,k) for pid,p in registry.items() for k,m in p.get('models',{}).items() if k.lower()=='hy4' or m.get('id','').lower()=='hy4']}))
