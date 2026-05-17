# Development Status

Last updated: 2026-05-17

## Purpose

This file tracks the current state of this fork so future work can start from the right baseline without having to reconstruct recent changes from commit history alone.

## Canonical Pipeline

- The single source of truth for the combined processing and roadmap pipeline now lives in `PIPELINE.md`.
- When checking what comes next, use the first stage marked `Next` in `PIPELINE.md`.

## Current Focus

- Stabilize the customized WebODM fork
- Add monitoring and progress workflows for repeated drone captures
- Reduce operational issues in local Docker and NodeODM setups

## Recently Completed

### Feature Validation Ledger

- Added a feature validation ledger for tracking whether features are untested, testing, tested, failing, or blocked
- Added admin and staff-only API access for feature validation records with area, evidence URL, test notes, and maintenance notes
- Added automatic tester/time stamping when a feature is marked tested
- Added structured `app.logger` entries when feature validation records are created or their status changes
- Added regression coverage for admin-only access, tested stamping, area/status filters, and status-change logging

### Client Sharing Portal

- Added project-scoped client share links with viewer and reviewer roles
- Added tokenized client portal access without requiring a WebODM user account or making the whole project public
- Added reviewer-only client comments with optional project task, issue, and GeoJSON geometry association
- Added portal JSON and comment APIs for integration with richer client review screens
- Added a lightweight client portal page that summarizes deliverables, open review items, access role, and comments
- Added regression coverage for share management permissions, anonymous portal access, reviewer comments, read-only viewer behavior, expired/disabled links, and portal rendering

### AI-Assisted Issue Detection

- Added server-side OpenAI API key and model settings under the singleton application Settings record
- Added a backend AI issue detection service that prepares safe image previews from field photos or orthophoto previews
- Added a project AI issue detection API that calls OpenAI from the server and creates reviewable `in_review` project issues
- Preserved the human-review loop by storing AI-created issues as normal project issues with AI metadata and confidence
- Added regression coverage for OpenAI request wiring, missing API key handling, issue creation, and project permissions

### Mobile/Field Photo Capture

- Added project-scoped field photo records for ground photos and 360 photos with GeoJSON point locations
- Added upload, list, update, and delete API support with project permission checks and optional task association
- Added map markers and photo popups for field photos in the 2D map
- Added a map camera control so project editors can attach a field photo to a clicked map location
- Added regression coverage for create/list/delete, file validation, location validation, and project permissions

### Design/BIM/Plan Overlays

- Added project-scoped design overlay records with upload, list, and delete API support
- Added permission checks so project viewers can load overlays and project editors can manage them
- Render supported GeoJSON and zipped Shapefile overlays automatically in the 2D map layer control
- Reused the existing map overlay parser path so temporary and persistent overlays stay consistent
- Added regression coverage for overlay create/list/delete, file validation, and project permissions

### Object Detection Stability

- Fixed object detection worker failures caused by serialized worker execution not having access to module-level imports
- Added regression coverage for object detection code paths
- Added ONNX compatibility handling for newer custom models, including the dog model case that required opset down-conversion for the runtime in this stack

### Monitoring And Progress MVP

- Added a first monitoring compare workflow for orthophotos in single-task map view
- Added a `Monitor` UI control to compare the current task with another completed task in the same project
- Implemented automatic alignment correction before overlay generation to compensate for small georeferencing drift from non-RTK flights
- Generated two outputs for review:
  - aligned comparison overlay
  - change heatmap overlay
- Added backend caching for generated monitoring products
- Added regression tests for alignment estimation and monitoring tile/API generation

### Project Timeline Monitoring

- Expanded monitoring from a single-task compare flow into a project-level timeline workspace
- Added a project monitoring timeline API that lists completed orthophoto tasks in timeline order
- Added timeline-driven reference and compare task selection in the map UI
- Added direct comparison launch from timeline-selected tasks instead of only from the current task context
- Added monitoring cache invalidation when orthophoto inputs change and when compared tasks are deleted
- Added regression coverage for timeline ordering and cache invalidation behavior

### DSM/DTM Delta And Cut/Fill

- Added optional DSM and DTM delta products to monitoring comparisons when both selected tasks have matching DEM assets
- Generated terrain delta tile overlays alongside the existing aligned orthophoto and change heatmap layers
- Added cut/fill-style volume summaries, net volume, delta range, and valid-pixel stats to terrain layers
- Extended monitoring cache invalidation to include DSM and DTM input timestamps
- Added regression coverage for terrain layer generation, tile serving, and orthophoto-only fallback behavior

### OneDrive Folder Task Intake

- Added a `onedriveintake` management command for creating WebODM import tasks from a OneDrive-synced local folder
- Supports zipped datasets and immediate child folders containing imagery
- Packages folder datasets into WebODM's existing `media/imports` flow and queues them with `pending_action=IMPORT`
- Tracks processed dataset fingerprints in a cache state file to avoid duplicate task creation on repeated runs
- Supports `WO_ONEDRIVE_INTAKE_DIR`, `--folder`, `--min-age`, `--dry-run`, and `--no-process`

### Change Issues And Annotations

- Added project-level issue and annotation tracking for detected changes, defects, progress notes, and review annotations
- Added nested project issue API endpoints with project-level permission checks and GeoJSON geometry validation
- Added a dashboard issues panel for creating issues, listing current issues, and updating issue status
- Added Django admin management and regression coverage for create/list/update, project permission enforcement, task ownership validation, and geometry validation

### Stakeholder Progress Reports

- Added a project progress report API for dashboard/client reporting
- Added printable stakeholder web reports with a `Print / Save PDF` action
- Reports summarize project metadata, task counts, latest deliverables, exported assets, and open issues/annotations
- Added a dashboard `Report` link for each project
- Added regression coverage for JSON reports, printable HTML, and project-scoped permissions

### Advanced Alignment

- Added similarity alignment metadata for monitoring comparisons, including transform type, rotation, scale, center point, and translation
- Added a conservative rotation/scale search path that runs only when the existing translation alignment has low confidence
- Updated aligned overlay transform and overlap bounds calculations to support similarity transforms instead of translation-only shifts
- Reduced alignment preview size to keep monitoring comparisons responsive while preserving full-resolution output generation
- Added regression coverage for translation stability and similarity-transform application

### Core Platform Hardening

- Added `ARCHITECTURE.md` and `MODULE_BOUNDARIES.md` to define core layer responsibilities, service boundaries, import direction, and upgrade-confidence rules
- Added `app/services/` as the application service layer
- Moved project progress report construction and HTML rendering from the API view into `app/services/project_reports.py`
- Added `ProjectPermissionPolicy` as a central project-scoped API permission entry point
- Updated newer project-scoped APIs to use the permission policy instead of duplicating direct project access checks
- Split monitoring implementation into focused services for alignment, cache, overlays, payloads, and product orchestration
- Removed the legacy `app/monitoring.py` compatibility facade and moved runtime callers to service imports
- Replaced the test-named async result abstraction with `worker/results.py` so runtime APIs and plugins do not import test plumbing

### Default NodeODM Repair

- Added a `syncdefaultnodes` management command to repair legacy default-node aliases such as `nodeodm`
- Reassigns tasks from stale default-node records to the current default node hostname
- Wired the command into startup so the stack can self-heal when default node aliases drift
- Added a regression test covering the legacy `nodeodm` hostname repair path

### Mission Planner Alias Cleanup

- Stopped startup warnings caused by the legacy `mission-planner` alias folder being discovered alongside the canonical `mission_planner` package
- Plugin discovery now prefers canonical underscore-named packages when a hyphenated legacy alias exists next to them
- Added regression coverage so hyphenated legacy aliases are skipped when a valid underscore twin is present

## What Is Working Now

- Standard WebODM task processing
- Default local WebODM UI on port `8000`
- Object detection, including the previously failing dog model path
- Monitoring compare for orthophotos with automatic translational alignment correction
- Monitoring alignment can now carry rotation and scale corrections when translation-only confidence is weak
- Monitoring compare from a project timeline view with timeline-based task selection
- DSM/DTM terrain delta overlays and cut/fill-style volume stats when compared tasks include DEM assets
- Project issues and annotations from the dashboard via each project's `Issues` panel
- Project field photos from the 2D map via the camera control and field-photo marker layer
- AI-assisted issue detection via server-side OpenAI configuration and the project issue review workflow
- Client sharing portal links with viewer/reviewer roles and tokenized client comments
- Feature validation ledger via `/api/feature-validations/` and Django admin for tested/untested/failing/blocked tracking
- Stakeholder progress reports from the dashboard via each project's `Report` link
- OneDrive-synced folder task intake via `python manage.py onedriveintake --project <id> --folder <path>`
- NodeODM stale-hostname repair via `python manage.py syncdefaultnodes --count 1`

## Known Limits

### Monitoring

- Monitoring still uses orthophoto-to-orthophoto comparison as the required alignment baseline
- DSM/DTM terrain products are available only when both compared tasks have matching DEM assets
- Advanced alignment is a conservative similarity transform; it is not full local/rubber-sheet warping yet
- No rubber-sheet/local warping or design/BIM comparison workflow yet

### Operations

- There is an unrelated local deletion at `nodeodm/external/NodeODM` that has intentionally been left untouched
- If a stale default processing node ever persists after a restart, you can repair it manually with `docker exec webapp python manage.py syncdefaultnodes --count 1`


## Useful Commands

```bash
docker compose build webapp
docker-compose up -d webapp worker
docker exec webapp python manage.py test app.tests.test_monitoring --keepdb
docker exec webapp python manage.py test app.tests.test_api_project_issues --keepdb
docker exec webapp python manage.py test app.tests.test_api_project_reports --keepdb
docker exec webapp python manage.py test app.tests.test_api_client_portal --keepdb
docker exec webapp python manage.py test app.tests.test_api_feature_validation --keepdb
docker exec webapp python manage.py test app.tests.test_onedrive_intake --keepdb
docker exec webapp python manage.py test app.tests.test_app.TestApp.test_syncdefaultnodes_repairs_legacy_default_node --keepdb
docker exec webapp python manage.py syncdefaultnodes --count 1
docker exec webapp python manage.py onedriveintake --project <project-id> --folder /webodm/app/media/imports/onedrive --dry-run
```
