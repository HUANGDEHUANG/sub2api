# Capability synchronization regression repair — 2026-09-09

Third-party Claude/Gemini relays were excluded from model-family enrichment.
Preview classified partial enrichment by database persistence despite deliberately
having no account ID. The registry cache retained newly missing models for six
hours. Warnings named neither missing models nor registry failures.

Known Claude and Gemini families now resolve against their own registry providers
alongside existing domestic/OpenAI families. Private IDs and unlisted variants do
not inherit guessed capabilities. Preview and saved sync use the same completeness
criteria. Responses include missing IDs, counts and a reason; all three admin UI
entry points display them. Cache lifetime is five minutes. Existing snapshots are
preserved on registry failure.

Run the RelayCapability, SyncUpstreamModelCatalog, FetchModelsDevMetadata,
LookupModelsDev, MatchModelsDev and AccountHandler model tests on every release.
Dockerfile.candidate enforces these plus the existing BUAGA custom-feature guards.
Frontend release verification includes the model-sync diagnostic tests.

Baseline: web-perf source plus the five image-preview backend files from the
currently deployed image-preview source. Preserve both prior custom changes.
Do not rebuild from the older quality-fixes pointer without these changes.

Live verification must check bbpccmax (464) and domestic accounts 356, 361, 377,
441, 448. An unlisted hy4 must remain explicitly unknown; hy4-preview is not
evidence of hy4 capabilities. Verify account credentials/mappings unchanged,
public settings and long notice unchanged, and candidate health before switching.
