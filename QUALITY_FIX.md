# BUAGA Quality Fixes - 2026-09-08

## Candidate

- Source: /home/serveradmin/candidates/buaga-v023-quality-fixes-20260908
- Image: sub2api:custom-v023-quality-fixes-20260908
- Release: buaga-custom-v0.2.3-quality-fixes-20260908
- Includes the preceding login captcha fix.
- Not activated. Production traffic and the default source pointer are unchanged.

## Changes

1. Preserve Codex manifest configuration across component updates and submission.
2. Resolve interval display prices using explicit-price priority, inherited base
   prices, and multipliers. Explicit zero remains zero. Billing is unchanged.
3. Hide composite groups in simple mode and remove only known composite IDs.
   Preserve unknown IDs while asynchronous group data is loading.
4. Restore subscription user links to filtered admin usage records.
5. Strictly validate local dates, reject calendar overflow and timezone suffixes,
   restore timezone fallback, and reuse it in the key usage page.
6. Restore missing translations and correct the misplaced Chinese simulation
   translation object; reuse the existing account-created message.
7. Archive the version-specific scheduler overlay. Both default entry points
   refuse execution. Historical reproduction also checks the exact old asset
   before changing files.
8. Require the complete frontend test suite and source build in the candidate
   Dockerfile. Package the generated assets from that verified stage, replacing
   rather than merging copied hashed chunks.

## Verification

- Local full frontend regression: 268 files, 1905 tests passed.
- pnpm verify:release passed (complete suite followed by production build).
- Modified-file ESLint and TypeScript checks passed.
- Date tests also passed under America/New_York.
- Browser component checks at desktop and 390px mobile widths passed: simple
  mode filtering, selection cleanup, interval price display, and no horizontal
  overflow. Browser data were local fixtures, not production accounts.
- The strengthened group test verifies the submitted update payload and closing
  the dialog after saving; it does not merely assert an on-screen toggle.
- Both legacy-script entry points were tested to refuse execution without
  changing the generated frontend.
- Previous 16 baseline failures are resolved, not skipped or removed.

## Boundaries

No database contents, balances, API keys, pricing configuration, scheduling
policy, production containers, nginx routes, or active source links were changed.
Old running containers remain pending a separate traffic/task/rollback inventory.
This is not a claim of a full security audit or measured scheduling performance
improvement.
