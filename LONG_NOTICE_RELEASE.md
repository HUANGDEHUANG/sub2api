# Long Notice Contract

Restored long_notice_content across admin request/response DTOs, settings storage, public settings and injected public settings JSON. Omitted admin update fields preserve the existing value; explicit empty strings clear it.

The saved 1211-character notice was not rewritten. Candidate public and admin settings exactly matched the database. All frontend files matched the previously active 18148 container by SHA256. Seven monitors were returned by the restored list-all route.

The Dockerfile runs LongNotice and settings regression tests before building. build-bluegreen.sh requires every notice backend layer, the regression test, and both monitor sorting routes. release.py verifies live notice contents against the database before allowing a switch; do not bypass these assertions.

Active: sub2api-v023-long-notice-20260908, 18149.
Rollback: sub2api-v023-monitor-sort-fix-r2-20260908, 18148.
Nginx backup: /home/serveradmin/.codex-backups/long-notice-20260908.
Old 18146 container was stopped to release database connections, not removed.
