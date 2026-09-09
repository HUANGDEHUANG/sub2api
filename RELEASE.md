# BUAGA v0.2.3 Preserved Upgrade

Base: buaga-custom-v0.2.2-scheduler-refinement-20260908, port 18145.
Upstream: Wei-Shaw/sub2api v0.2.3, commit 8fa67d477d6651a744754392a8982ea589c26ae6.

Applied the full official v0.2.2-to-v0.2.3 backend delta. The existing display-name fallback overlapped the official change; retained it and added the official model type fallback. Embedded and build version are 0.2.3 (the upstream tag's VERSION file lags the release).

All other custom source is preserved. All frontend release files are byte-identical to the scheduler-refinement baseline. The custom scheduler overlay, version badge, model plaza and BUAGA layout are unchanged. Do not rebuild the approved frontend bundle casually; follow existing preservation validation.

Passed targeted Go tests for official Ollama/model/migration fixes and custom scheduling, whitelist and plaza behavior. PostgreSQL temporary-table tests verified migration 236 rename, replay, backfill preservation and missing-column repair, then rolled back. Full database backup retained and archive catalog validated.

Candidate verification compared all frontend file hashes, environment, mounts, network and public settings (except version); checked accounts 440/397/242/431 against saved model mappings; checked groups/users/subscriptions and update APIs. Current/latest both 0.2.3, no update available.

Active: sub2api-v023-preserved-20260908, loopback 18146.
Rollback: sub2api-v022-scheduler-refinement-20260908, loopback 18145, retained running.
Nginx backup: /home/serveradmin/.codex-backups/upgrade-v023-switch-20260908/sub2api-global.conf.
Database backup: /home/serveradmin/.codex-backups/upgrade-v023-data-20260908/sub2api.dump.

Migration 236 did not change existing group values. Both compatibility columns and the existing synchronization trigger remain. Routine rollback uses the retained application/config; do not restore the full database over live traffic and newer usage records.
