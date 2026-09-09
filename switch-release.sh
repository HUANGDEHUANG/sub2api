#!/usr/bin/env bash
set -Eeuo pipefail
release=/home/serveradmin/candidates/buaga-v022-scheduler-recovery-20260908
active_config=/etc/nginx/conf.d/sub2api-global.conf
backup=/home/serveradmin/.codex-backups/scheduler-recovery-20260908

exec 9>/home/serveradmin/.buaga-deploy.lock
flock -n 9
sudo -n python3 "$release/verify-release.py"
sudo -n cmp "$release/nginx-before.conf" "$active_config"
test ! -e "$backup"
mkdir -p "$backup"
sudo -n cp -a "$active_config" "$backup/sub2api-global.conf"
cp -a /home/serveradmin/buaga-bluegreen-build.sh "$backup/buaga-bluegreen-build.sh"
cp -a /home/serveradmin/validate-candidate-image.sh "$backup/validate-candidate-image.sh"

rollback() {
    trap - ERR
    sudo -n install -m 0644 "$backup/sub2api-global.conf" "$active_config.rollback"
    sudo -n mv "$active_config.rollback" "$active_config"
    sudo -n nginx -t
    sudo -n systemctl reload nginx
    printf 'Switch verification failed; original upstream restored.\n' >&2
    exit 1
}
trap rollback ERR
sudo -n install -m 0644 "$release/nginx-after.conf" "$active_config.next"
sudo -n mv "$active_config.next" "$active_config"
sudo -n nginx -t
sudo -n systemctl reload nginx
curl --fail --silent --show-error --max-time 15 --resolve buaga.dpdns.org:443:127.0.0.1 https://buaga.dpdns.org/health
sudo -n grep -F 'server 127.0.0.1:18136;' "$active_config"
trap - ERR
printf '\nBlue-green switch complete; original instance remains available for active requests and rollback.\n'
