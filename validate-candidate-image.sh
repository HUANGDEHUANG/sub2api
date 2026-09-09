#!/usr/bin/env bash
# Reject mislabeled or non-BUAGA images before a blue-green switch.

set -euo pipefail

IMAGE_REF="${1:-${BUILD_IMAGE_TAG:-sub2api:custom-v0.2.2-buaga-scheduler-recovery-20260908}}"
EXPECTED_VERSION="${EXPECTED_VERSION:-0.2.2}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-buaga-custom-v0.2.2-scheduler-recovery-20260908}"
RETIRED_ENTRY="${RETIRED_FRONTEND_ENTRY:-index-CBAvwpcd.js}"

die() { printf 'candidate validation: %s\n' "$*" >&2; exit 1; }

if docker info >/dev/null 2>&1; then
  docker_cmd=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  docker_cmd=(sudo -n docker)
else
  die "Docker is unavailable for this user"
fi

"${docker_cmd[@]}" image inspect "${IMAGE_REF}" >/dev/null 2>&1 \
  || die "candidate image does not exist: ${IMAGE_REF}"

version_output="$("${docker_cmd[@]}" run --rm --entrypoint /app/sub2api "${IMAGE_REF}" --version 2>&1)" \
  || die "candidate binary cannot report its version"
grep -Fq "${EXPECTED_VERSION}" <<<"${version_output}" \
  || die "binary version is not ${EXPECTED_VERSION}: ${version_output}"
grep -Fq "${EXPECTED_COMMIT}" <<<"${version_output}" \
  || die "binary commit is not ${EXPECTED_COMMIT}: ${version_output}"

"${docker_cmd[@]}" run --rm --entrypoint /bin/sh "${IMAGE_REF}" -eu -c '
  cd /app/.buaga-release
  test -f /app/.buaga-release/index.html
  grep -Fq "BuaGa" index.html
  set -- assets/HomeView-*.js; test "$#" -eq 1; test -f "$1"
  set -- assets/LoginView-*.js; test "$#" -eq 1; test -f "$1"; grep -Fq "BuaGa" "$1"; grep -Fq "login_captcha_enabled" "$1"
  set -- assets/AppLayout*.js; test "$#" -eq 1; test -f "$1"; grep -Fq "long_notice_content" "$1"
  set -- assets/AnnouncementsView-*.js; test "$#" -eq 1; test -f "$1"; grep -Fq "long_notice_content" "$1"
  set -- assets/SettingsView-*.js; test "$#" -eq 1; test -f "$1"; grep -Fq "long_notice_content" "$1"
  set -- assets/ChannelMonitorView-*.js; test "$#" -eq 1; test -f "$1"; grep -Fq "monitor-sort-handle" "$1"
  grep -Fq "/admin/channel-monitors/sort-order" assets/index-*.js
  ! grep -Fq "index-CBAvwpcd.js" index.html
' >/dev/null || die "image does not contain the approved BUAGA frontend release"

strings_output="$("${docker_cmd[@]}" run --rm --entrypoint /bin/sh "${IMAGE_REF}" -c \
  'grep -a -o -e long_notice_content -e "channel monitor sort order cannot be empty" -e login_captcha_enabled /app/sub2api 2>/dev/null || true')"
grep -Fq 'long_notice_content' <<<"${strings_output}" \
  || die "candidate backend is missing the BUAGA long-notice setting contract"
grep -Fq 'channel monitor sort order cannot be empty' <<<"${strings_output}" \
  || die "candidate backend is missing the channel monitor sort service"
grep -Fq 'login_captcha_enabled' <<<"${strings_output}" \
  || die "candidate backend is missing the login captcha switch"

printf 'candidate validation: PASS image=%s version=%s commit=%s frontend=dynamic-approved-buaga\n' \
  "${IMAGE_REF}" "${EXPECTED_VERSION}" "${EXPECTED_COMMIT}"
