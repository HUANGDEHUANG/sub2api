import hashlib, subprocess
from pathlib import Path

source = Path('/home/serveradmin/candidates/buaga-v023-announcement-status-20260909')
old = Path('/home/serveradmin/candidates/buaga-v023-announcement-close-20260909')
backup = Path('/home/serveradmin/.codex-backups/announcement-status-20260909')
assert 'server 127.0.0.1:18158;' in Path('/etc/nginx/conf.d/sub2api-global.conf').read_text()
assert Path('/home/serveradmin/candidates/buaga-current-custom').resolve() == old
# This is a frontend-only release. Do not refresh a baseline if server code differs.
subprocess.run(['diff','-qr','--exclude=dist',str(old/'backend'),str(source/'backend')],check=True,capture_output=True)
query = "SELECT json_agg(x ORDER BY id) FROM (SELECT id,credentials,extra-'upstream_model_metadata'-'upstream_billing_probe' AS extra FROM accounts WHERE id IN (356,361,377,441,448,464)) x"
data = subprocess.check_output(['docker','exec','sub2api-return-postgres','psql','-U','sub2api','-d','sub2api','-Atc',query],text=True).strip()
original = backup/'account-identity-before-probe-normalization.sha256'
assert not original.exists()
(backup/'account-identity.sha256').rename(original)
(backup/'account-identity.sha256').write_text(hashlib.sha256(data.encode()).hexdigest())
print('Backend source equality verified; preserved prior fingerprint and excluded only runtime probe cache. Database not modified.')
