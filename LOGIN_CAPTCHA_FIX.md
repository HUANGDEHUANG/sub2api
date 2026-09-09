# Login Captcha Fix - 2026-09-08

## Scope

Based on the production source at:
`/home/serveradmin/candidates/buaga-v023-long-notice-20260908`.

Candidate:
`/home/serveradmin/candidates/buaga-v023-login-captcha-fix-20260908`.

Image: `sub2api:custom-v023-login-captcha-fix-20260908`.

- Restore the existing login-only captcha setting in the public API, injected
  startup settings, and password-login handler.
- Missing or invalid settings retain verification. Configuration read failures
  reject login. Production Turnstile.Required overrides login-only opt-out.
- Registration, email verification, and password-reset verification are unchanged.
- Share SDK loading, bound loading to 15 seconds, allow retry, and invalidate
  pending component initialization after navigation.
- Block login when public security settings cannot load; offer a page reload.
- Add backend build checks and regression tests.

## Verification

- Captcha component and auth API tests: 10 passed.
- Backend settings, login captcha, captcha providers, and long-notice tests passed
  in service, handler, and admin handler packages.
- TypeScript checking, changed-component ESLint, and production frontend build passed.
- Browser checks on desktop and 390px mobile: failed loading remains visible,
  login is disabled without a proof, retry can recover, and the login-only
  disabled setting removes the widget.
- Browser recovery used a mocked SDK on localhost. No real user login was
  submitted and this is not a claim of passing Cloudflare's real challenge.

## Release Hold

The historical frontend test hold below was resolved by the subsequent quality
fixes. See QUALITY_FIX.md for the combined candidate and current verification.
The production switch still has not been performed.

No production switch or database/settings update was performed.
The production source pointer and nginx upstream remained at long-notice / 18149.

Full frontend regression: 1882 passed, 16 failed (268 files).
All 16 failures were reproduced in the unmodified baseline (7 affected files):
locale completeness, datetime helpers, interval pricing, SupportedModelChip,
GroupSelector, GroupsView Codex binding, and subscription user usage links.
These pre-existing failures were not modified as part of the login fix.
Do not report the full test suite as passing.
