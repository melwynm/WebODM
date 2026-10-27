# Application Improvement Plan

Date: 2026-09-06

This plan supports the QA-hardening priority in `PIPELINE.md`, which remains the canonical pipeline. It does not change the P1–P15 roadmap order.

## Current evidence

- The existing AI review, monitoring panel, and project issues frontend suites passed: 3 suites, 7 tests. This was a baseline run before the new fixes, not validation of the changes below.
- Review identified stale frontend responses, enabled read-only status controls, background dispatch before transaction commit, and worker completion updates that could overwrite a newer run state.
- Initial edits exist in AI review controls, monitoring dispatch/retry handling, and worker completion guards. They need review and regression tests before being considered complete.
- The working tree already contains substantial ongoing feature work. Keep improvements scoped and preserve that work.

## Ordered work

| Order | Work | Completion criteria |
| --- | --- | --- |
| 1 | Finish monitoring job reliability. Dispatch after commit, save the job identifier before dispatch, serialize concurrent starts and retries, and accept worker results only for the current generating attempt. | Tests cover commit and rollback, concurrent requests, queue failure, retries, and late success/failure after a newer attempt or publication. Existing monitoring API tests pass with real commit behavior. |
| 2 | Make monitoring and AI review safe during pending requests. Ignore stale polling/preview results after selection changes; prevent conflicting submissions; keep signed previews tied to the selected source and survey pair. | Deferred-response tests prove that switching runs cannot restore an old selection or attach another run's preview. Duplicate actions are blocked and errors restore usable controls. |
| 3 | Correct issue status controls. Honor edit permissions, prevent overlapping saves for the same issue, and give status selectors accessible names. | Read-only users cannot initiate updates; editors can save once, recover from errors, and operate controls by keyboard. |
| 4 | Improve client comment validation. Validate name length, email, and required content before saving; preserve entered values and show field errors on invalid submissions. | Browser-form tests cover invalid and oversized input without server errors, preserved drafts, successful submissions, and viewer restrictions. |
| 5 | Verify the integrated workflow. Run focused backend/frontend regressions, a production frontend build, migration checks, and platform audit. Smoke-test survey selection → comparison → AI preview → confirmation → report publication in a test project. | Results are recorded, published snapshots remain stable, expired/disabled shares are rejected, and browser behavior agrees with API permissions. Use an isolated test database and synthetic data. |
| 6 | Record evidence and prepare the local release. Update development notes and the affected feature validation records, then rebuild application assets and verify the running version when applying the release. | Only features actually exercised are marked tested; remaining gaps are explicit; the deployed version has passed smoke checks. |

## Follow-up review after these fixes

- Measure dashboard and monitoring history performance on larger projects before selecting query or rendering optimizations.
- Check mobile layout, keyboard navigation, loading indicators, and actionable error messages across the main project workflow.
- Audit the remaining P1–P15 validation records and choose subsequent work from observed failures or missing evidence.

## Delivery sequence

Finish orders 1–3 as one reliability pass, then order 4 as a separate form-validation change. Complete orders 5–6 before describing these improvements as verified or deployed.
