# Development Status

Last updated: 2026-03-19

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
- Monitoring compare from a project timeline view with timeline-based task selection
- NodeODM stale-hostname repair via `python manage.py syncdefaultnodes --count 1`

## Known Limits

### Monitoring

- Monitoring currently targets orthophoto-to-orthophoto comparison only
- Alignment correction is translational only
- No rotation, scale, rubber-sheet, DSM-delta, volume-delta, OneDrive-folder intake, or design/BIM comparison workflow yet

### Operations

- There is an unrelated local deletion at `nodeodm/external/NodeODM` that has intentionally been left untouched
- If a stale default processing node ever persists after a restart, you can repair it manually with `docker exec webapp python manage.py syncdefaultnodes --count 1`


## Useful Commands

```bash
docker compose build webapp
docker-compose up -d webapp worker
docker exec webapp python manage.py test app.tests.test_monitoring --keepdb
docker exec webapp python manage.py test app.tests.test_app.TestApp.test_syncdefaultnodes_repairs_legacy_default_node --keepdb
docker exec webapp python manage.py syncdefaultnodes --count 1
```
