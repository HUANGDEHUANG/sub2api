import datetime, hashlib, json, os, re, subprocess, tempfile
from pathlib import Path

source = Path('/home/serveradmin/candidates/buaga-v023-announcement-status-20260909')
backup = Path('/home/serveradmin/.codex-backups/announcement-status-20260909')
assert 'server 127.0.0.1:18159;' in Path('/etc/nginx/conf.d/sub2api-global.conf').read_text()
stage = Path(tempfile.mkdtemp(prefix='announcement-dist-',dir=source))
os.chmod(stage,0o755)
subprocess.run(['docker','cp','sub2api-v023-announcement-status-20260909:/app/.buaga-release/.',str(stage)],check=True)
assert (stage/'index.html').is_file()
dist = source/'backend/internal/web/dist'
dist.rename(backup/'frontend-before-announcement-status')
stage.rename(dist)
release = json.loads((source/'CURRENT_RELEASE.json').read_text())
release['verification'] = {'backend_build_regressions':'passed','frontend_release_verification':'passed','announcement_dismissal_cases':10,'public_admin_settings_long_notice':'unchanged','announcement_content_and_configuration':'unchanged','sampled_account_credentials_and_configuration':'unchanged','channel_order':'unchanged','image_authentication':'passed','log_rotation':'50m x 5','image_builds':1}
files = ['backend/internal/service/upstream_models.go','backend/internal/service/image_preview.go','backend/internal/service/upstream_balance_guard.go','backend/internal/service/gemini_messages_compat_service.go','backend/internal/service/gemini_chat_completions_compat_service.go','backend/internal/service/openai_images.go','backend/internal/handler/failover_loop.go','frontend/src/components/admin/usage/UsageTable.vue','Dockerfile.candidate','BUAGA_RELEASE_COMMIT']
files += ['frontend/src/stores/announcements.ts','frontend/src/components/common/__tests__/AnnouncementBell.spec.ts']
files += ['frontend/src/components/common/AnnouncementBell.vue','frontend/src/i18n/locales/zh/misc.ts','frontend/src/i18n/locales/en/misc.ts']
release['verification'].update({'frontend_test_files':270,'frontend_tests':1919})
release['source_hashes'] = {p:hashlib.sha256((source/p).read_bytes()).hexdigest() for p in files}
(source/'CURRENT_RELEASE.json').write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
print('Release manifest and clean frontend artifacts saved; previous artifacts retained.')
