import fcntl
import pathlib
import shutil
import subprocess

lock = open('/home/serveradmin/.buaga-deploy.lock', 'a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
release = pathlib.Path('/home/serveradmin/candidates/buaga-v022-scheduler-refinement-20260908')
current = pathlib.Path('/home/serveradmin/candidates/buaga-current-custom')
assert current.resolve() == pathlib.Path('/home/serveradmin/candidates/buaga-v022-version-badge-20260908'), 'Default source changed; abort'
subprocess.run(['python3', str(release / 'deploy-model-list.py'), 'verify'], check=True)
config = pathlib.Path('/etc/nginx/conf.d/sub2api-global.conf')
before = config.read_text()
old = '    server 127.0.0.1:18140;'
new = '    server 127.0.0.1:18145;'
assert before.count(old) == 1 and new not in before, 'Active release changed; switch aborted'
backup = pathlib.Path('/home/serveradmin/.codex-backups/scheduler-refinement-20260908')
backup.mkdir(exist_ok=False)
shutil.copy2(config, backup / config.name)
try:
    temporary = config.with_suffix('.pending')
    temporary.write_text(before.replace(old, new, 1))
    temporary.chmod(config.stat().st_mode & 0o777)
    temporary.replace(config)
    subprocess.run(['nginx', '-t'], check=True)
    subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    subprocess.run(['curl', '--fail', '--silent', '--show-error', '--max-time', '15', '--resolve', 'buaga.dpdns.org:443:127.0.0.1', 'https://buaga.dpdns.org/health'], check=True)
    temporary_link = current.with_name('buaga-current-custom.pending')
    temporary_link.symlink_to(release)
    temporary_link.replace(current)
except Exception:
    shutil.copy2(backup / config.name, config)
    subprocess.run(['nginx', '-t'], check=True)
    subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    raise
print('\nScheduler refinement switched successfully; old instance retained')
