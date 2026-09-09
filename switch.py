import fcntl
import pathlib
import shutil
import subprocess

lock = open('/home/serveradmin/.buaga-deploy.lock', 'a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
release = pathlib.Path('/home/serveradmin/candidates/buaga-v023-preserved-20260908')
subprocess.run(['python3', str(release / 'deploy-upgrade.py'), 'verify'], check=True)
config = pathlib.Path('/etc/nginx/conf.d/sub2api-global.conf')
before = config.read_text()
old = '    server 127.0.0.1:18145;'
new = '    server 127.0.0.1:18147;'
assert before.count(old) == 1 and new not in before, 'Active release changed; switch aborted'
backup = pathlib.Path('/home/serveradmin/.codex-backups/upgrade-v023-switch-20260908')
backup.mkdir(exist_ok=False)
shutil.copy2(config, backup / config.name)
try:
    config.write_text(before.replace(old, new, 1))
    subprocess.run(['nginx', '-t'], check=True)
    subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    subprocess.run(['curl', '--fail', '--silent', '--show-error', '--max-time', '15', '--resolve', 'buaga.dpdns.org:443:127.0.0.1', 'https://buaga.dpdns.org/health'], check=True)
except Exception:
    shutil.copy2(backup / config.name, config)
    subprocess.run(['nginx', '-t'], check=True)
    subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    raise
print('\nChannel monitor sort fix switched successfully; old instance retained')
