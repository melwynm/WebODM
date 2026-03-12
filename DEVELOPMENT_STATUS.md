# Development Status

Last updated: 2026-03-12

## Purpose

This file tracks the current state of this fork so future work can start from the right baseline without having to reconstruct recent changes from commit history alone.

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

### Default NodeODM Repair

- Added a `syncdefaultnodes` management command to repair legacy default-node aliases such as `nodeodm`
- Reassigns tasks from stale default-node records to the current default node hostname
- Wired the command into startup so the stack can self-heal when default node aliases drift
- Added a regression test covering the legacy `nodeodm` hostname repair path

## What Is Working Now

- Standard WebODM task processing
- Default local WebODM UI on port `8000`
- Object detection, including the previously failing dog model path
- Monitoring compare for orthophotos with automatic translational alignment correction
- NodeODM stale-hostname repair via `python manage.py syncdefaultnodes --count 1`

## Known Limits

### Monitoring

- Monitoring currently targets orthophoto-to-orthophoto comparison only
- The workflow is currently focused on a single task view, not a full project timeline workspace
- Alignment correction is translational only
- No rotation, scale, rubber-sheet, DSM-delta, volume-delta, or design/BIM comparison workflow yet

### Operations

- There is an unrelated local deletion at `nodeodm/external/NodeODM` that has intentionally been left untouched
- The `mission-planner` plugin still logs warnings during startup in this environment
- If a stale default processing node ever persists after a restart, you can repair it manually with `docker exec webapp python manage.py syncdefaultnodes --count 1`

## Recommended Next Steps

1. Extend monitoring from orthophoto compare into a proper project timeline view
2. Add DSM/DTM delta and cut/fill change products
3. Promote detected changes into issues/annotations with status tracking
4. Improve alignment from translation-only to affine or feature-based local warping
5. Add exportable monitoring/progress reports for stakeholders

## Useful Commands

```bash
docker compose build webapp
docker-compose up -d webapp worker
docker exec webapp python manage.py test app.tests.test_monitoring --keepdb
docker exec webapp python manage.py test app.tests.test_app.TestApp.test_syncdefaultnodes_repairs_legacy_default_node --keepdb
docker exec webapp python manage.py syncdefaultnodes --count 1
```
