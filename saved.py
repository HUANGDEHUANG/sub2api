import json, subprocess
q="""SELECT json_agg(x) FROM (
SELECT a.id,a.name,a.extra->'upstream_model_metadata'->>'synced_at' AS synced_at,
(SELECT count(*) FROM jsonb_object_keys(a.extra->'upstream_model_metadata'->'models')) AS saved_models
FROM accounts a WHERE id IN (356,361,377,441,448,464) ORDER BY id) x"""
result=subprocess.check_output(['sudo','-n','docker','exec','sub2api-return-postgres','psql','-U','sub2api','-d','sub2api','-Atc',q],text=True)
data=json.loads(result)
assert {x['id']:x['saved_models'] for x in data}=={356:4,361:2,377:2,441:25,448:11,464:11}
print(json.dumps(data,ensure_ascii=False))
