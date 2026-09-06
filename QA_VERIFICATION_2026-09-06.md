# Integrated QA Verification

Date: 2026-09-06

Scope: improvement-plan item 5, covering the monitoring workflow from survey comparison through AI review and client report publication. All application data used by the regression suite was created in Django's isolated test database with synthetic raster assets.

## Result

The integrated workflow passed. The checks covered survey-pair selection and readiness, comparison product generation, AI preview and signed confirmation, issue updates, report publication, client portal access, and frontend request-state behavior.

| Check | Result | Evidence |
| --- | --- | --- |
| Backend workflow regression | Pass | 47 tests in 757.840 seconds |
| Frontend workflow regression | Pass | 3 suites, 15 tests in 8.167 seconds |
| Django model migration generation | Pass | `makemigrations --check --dry-run` reported no changes |
| Applied migration plan | Pass | `migrate --plan` reported no planned operations |
| Platform audit | Pass | 108 checks passed; 0 missing; 0 errors |
| Production frontend bundle | Pass with existing warnings | Webpack 5.105.4 compiled in 28.192 seconds |

## Workflow evidence

- Monitoring tests create project tasks with synthetic orthophotos and elevation models, select a survey pair, generate aligned and change layers, validate volume statistics, serve generated PNG tiles, and verify cache invalidation and cleanup.
- Monitoring-run tests cover queued work, current-attempt ownership, retry and dispatch failures, exact-pair AI preview and confirmation, publication, stable saved report snapshots, and client portal report access.
- AI tests verify that confirmation creates the exact previewed candidates without a second model request, rejects tampered confirmations, and enforces project permissions.
- Client portal tests reject disabled and expired shares, enforce viewer restrictions, validate comments, preserve invalid drafts, and accept valid submissions.
- Frontend tests verify stale response rejection, duplicate-action prevention, error recovery, publication behavior, editable versus read-only issue controls, and accessible status inputs.

## Commands

```text
python manage.py test app.tests.test_api_monitoring_runs app.tests.test_api_ai_issue_detection app.tests.test_api_project_issues app.tests.test_api_client_portal app.tests.test_api_project_reports app.tests.test_monitoring --noinput
npm run qtest -- --runInBand AIIssueDetectionPanel MonitoringRunPanel ProjectIssuesPanel
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py platformaudit
webpack --config webpack.config.js --mode production
```

## Existing build warnings

The production bundle completed with 52 warnings already present in the build configuration: the Sass legacy JavaScript API deprecation, Webpack's `[hash]` deprecation, and recommended asset or entrypoint size limits. The generated application bundles completed successfully. The `build:production` package script currently passes a positional `production` argument that Webpack CLI rejects; the equivalent explicit `--mode production` command above is the successful production-build check.
