#!/usr/bin/env bash
# Build a Sub2API blue-green candidate with the approved BUAGA frontend.
# The frontend source is explicit and validated so a normal source refresh
# cannot silently replace the custom UI with the upstream bundle.

set -euo pipefail

REPO_ROOT="${BUILD_REPO_ROOT:-/home/serveradmin/candidates/buaga-current-custom}"
FRONTEND_SOURCE="${BUILD_FRONTEND_SOURCE:-${REPO_ROOT}/backend/internal/web/dist}"
DOCKERFILE="${BUILD_DOCKERFILE:-${REPO_ROOT}/Dockerfile.candidate}"
IMAGE_TAG="${BUILD_IMAGE_TAG:-sub2api:custom-buaga-candidate}"
VALIDATOR="${BUILD_VALIDATOR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/validate-candidate-image.sh}"

die() {
  printf 'blue-green build: %s\n' "$*" >&2
  exit 1
}

[[ -d "${REPO_ROOT}" ]] || die "repository root does not exist: ${REPO_ROOT}"
[[ -f "${DOCKERFILE}" ]] || die "candidate Dockerfile does not exist: ${DOCKERFILE}"
[[ -d "${FRONTEND_SOURCE}" ]] || die "approved frontend source does not exist: ${FRONTEND_SOURCE}"

[[ -f "${REPO_ROOT}/BUAGA_RELEASE_COMMIT" ]] || die "release identity is missing"
VERSION="${BUILD_VERSION:-$(tr -d '[:space:]' < "${REPO_ROOT}/backend/cmd/server/VERSION")}"
COMMIT="${BUILD_COMMIT:-$(tr -d '[:space:]' < "${REPO_ROOT}/BUAGA_RELEASE_COMMIT")}"
[[ "${COMMIT}" == "buaga-custom-v${VERSION}-"* ]] || die "source version and custom release identity do not match"
[[ "${IMAGE_TAG}" == sub2api:custom-* ]] || die "a BUAGA custom image tag is required"

[[ "${FRONTEND_SOURCE}" -ef "${REPO_ROOT}/backend/internal/web/dist" ]] \
  || die "the approved frontend must be staged in the embedded dist before building"
[[ -f "${FRONTEND_SOURCE}/index.html" ]] || die "approved frontend entry is missing"
grep -Fq 'BuaGa' "${FRONTEND_SOURCE}/index.html" || die "BUAGA frontend branding is missing"
require_asset_marker() {
  local pattern="$1" marker="$2" label="$3" matches=()
  shopt -s nullglob
  matches=("${FRONTEND_SOURCE}"/assets/${pattern})
  shopt -u nullglob
  [[ "${#matches[@]}" -eq 1 ]] || die "expected exactly one ${label} asset"
  [[ -z "${marker}" ]] || grep -Fq "${marker}" "${matches[0]}" \
    || die "${label} is missing required marker: ${marker}"
}

require_asset_marker 'HomeView-*.js' '' 'BUAGA home'
require_asset_marker 'LoginView-*.js' 'BuaGa' 'BUAGA login'
require_asset_marker 'LoginView-*.js' 'login_captcha_enabled' 'login captcha switch'
require_asset_marker 'AppLayout*.js' 'long_notice_content' 'notification bell'
require_asset_marker 'AnnouncementsView-*.js' 'long_notice_content' 'announcement editor'
require_asset_marker 'SettingsView-*.js' 'long_notice_content' 'notification settings'
require_asset_marker 'ChannelMonitorView-*.js' 'monitor-sort-handle' 'channel monitor sorting'
grep -Fq '/admin/channel-monitors/sort-order' "${FRONTEND_SOURCE}"/assets/index-*.js \
  || die "channel monitor sort API is missing"
grep -R -Fq 'channel monitor sort order cannot be empty' "${REPO_ROOT}/backend/internal/service" \
  || die "channel monitor sorting backend is missing"
grep -R -Fq 'GetSchedulerSnapshot' "${REPO_ROOT}/backend/internal/service" \
  || die "scheduler monitoring backend is missing"
for notice_file in service/setting_public.go service/setting_update.go service/setting_parse.go service/settings_view.go handler/setting_handler.go handler/dto/settings.go handler/admin/setting_handler.go handler/admin/setting_handler_update.go; do
  grep -Fq 'LongNoticeContent' "${REPO_ROOT}/backend/internal/${notice_file}" \
    || die "long notice contract missing in ${notice_file}"
done
grep -Fq 'TestLongNoticePublicAndSave' "${REPO_ROOT}/backend/internal/service/long_notice_regression_test.go" \
  || die "long notice regression test missing"
grep -Fq 'h.Admin.ChannelMonitor.ListAll' "${REPO_ROOT}/backend/internal/server/routes/admin.go" \
  || die "channel monitor list-all route missing"
grep -Fq 'h.Admin.ChannelMonitor.UpdateSortOrder' "${REPO_ROOT}/backend/internal/server/routes/admin.go" \
  || die "channel monitor sort route missing"
grep -Fq 'TestRelayCapabilitySyncPlatformMatrix' "${REPO_ROOT}/backend/internal/service/upstream_models_relay_regression_test.go" \
  || die "cross-platform capability sync regression tests missing"
grep -Fq 'RelayCapability' "${DOCKERFILE}" \
  || die "candidate build no longer enforces capability sync regression tests"
grep -Fq 'RuntimeHardening' "${DOCKERFILE}" \
  || die "candidate build no longer enforces runtime hardening regressions"
build_cmd=(docker build
  --build-arg GOPROXY=https://goproxy.cn,direct
  --build-arg GOSUMDB=sum.golang.google.cn
  --build-arg "VERSION=${VERSION}"
  --build-arg "COMMIT=${COMMIT}"
  -t "${IMAGE_TAG}"
  -f "${DOCKERFILE}"
  "${REPO_ROOT}"
)
printf 'blue-green build: frontend=%s\n' "${FRONTEND_SOURCE}"
printf 'blue-green build: dockerfile=%s\n' "${DOCKERFILE}"
printf 'blue-green build: image=%s\n' "${IMAGE_TAG}"
printf 'blue-green build: command='; printf ' %q' "${build_cmd[@]}"; printf '\n'

[[ "${DRY_RUN:-0}" == "1" ]] && exit 0

if docker info >/dev/null 2>&1; then
  "${build_cmd[@]}"
elif sudo -n docker info >/dev/null 2>&1; then
  sudo -n "${build_cmd[@]}"
else
  die "Docker is unavailable for this user"
fi

[[ -x "${VALIDATOR}" ]] || die "candidate validator is missing or not executable: ${VALIDATOR}"
EXPECTED_VERSION="${VERSION}" EXPECTED_COMMIT="${COMMIT}" "${VALIDATOR}" "${IMAGE_TAG}"
