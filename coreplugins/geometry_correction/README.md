# Geometry Correction

This plugin adds post-processing geometry correction to completed WebODM tasks.
It now follows the standard WebODM plugin layout and loads from:

- `coreplugins/geometry_correction/plugin.py`
- `coreplugins/geometry_correction/manifest.json`
- `coreplugins/geometry_correction/public/main.js`

The implementation package lives in `coreplugins/geometry_correction/geometry_correction/`.

## Features

- Semantic-aware plane classification for walls, floors, roofs, ramps, and unknown surfaces.
- Per-class correction profiles so wall, floor, roof, and ramp snapping can use different thresholds.
- Orthophoto confidence maps written as GeoTIFFs with coverage percentages.
- Completion webhooks with optional HMAC signing.
- Task-local job state persisted to `data/geometry_correction_status.json`.
- Corrected outputs written to `assets/geometry_correction/`.

## Runtime behavior

- The plugin runs against completed WebODM tasks.
- It stores job state per task instead of relying on a standalone Django model.
- The browser UI polls `/api/plugins/geometry_correction/status/<task_id>/`.
- The worker writes progress, result payloads, and failure details back to the task status file.

## API

- `POST /api/plugins/geometry_correction/correct/`
- `GET /api/plugins/geometry_correction/status/<task_id>/`
- `POST /api/plugins/geometry_correction/task/<task_id>/correct`
- `GET /api/plugins/geometry_correction/task/<task_id>/status`

Request body for `correct/`:

```json
{
  "task_id": "task-uuid",
  "project_id": 1,
  "options": {
    "plane_threshold": 0.05,
    "snap_threshold": 0.05,
    "line_tolerance": 2.0,
    "correct_pointcloud": true,
    "correct_mesh": true,
    "correct_orthophoto": true,
    "use_semantic_profiles": true,
    "generate_confidence_map": true,
    "webhook_url": "",
    "webhook_secret": ""
  }
}
```

## Outputs

Typical outputs are written under `assets/geometry_correction/`:

- `odm_georeferenced_model_corrected.ply` or `.laz`
- `odm_georeferenced_model_mesh_corrected.ply`
- `odm_orthophoto_corrected.tif`
- `odm_orthophoto_corrected_confidence.tif`

## Dependencies

Install plugin dependencies from the plugin root for manual, non-Docker setups:

```bash
pip install -r coreplugins/geometry_correction/requirements.txt
```

Core optional runtime dependencies:

- `open3d`
- `laspy[lazrs]`
- `opencv-python-headless`
- `rasterio`
- `scipy`
- `requests`

The WebODM Docker image now installs `coreplugins/geometry_correction/requirements.txt`
during build and includes the required OpenGL runtime libraries for Open3D
(`libgl1` and `libglib2.0-0`).

## Tests

The plugin test suite lives in `coreplugins/geometry_correction/geometry_correction/tests/`.

The current suite covers:

- Existing point-cloud and orthophoto math helpers.
- Semantic classification and correction profiles.
- Confidence-map generation and orthophoto stats.
- Webhook signing and task-level webhook firing.
- Plugin root packaging and API mount-point registration.

Example container run:

```bash
docker exec webapp /bin/bash -lc "cd /webodm && export PYTHONPATH=/webodm:/webodm/coreplugins/geometry_correction:$PYTHONPATH && python -m unittest discover -s /webodm/coreplugins/geometry_correction/geometry_correction/tests -t /webodm/coreplugins/geometry_correction -v"
```

Outside the Docker image, some integration tests remain environment-dependent:

- OpenCV-backed Hough detection tests are skipped when OpenCV is not installed.
- Open3D-backed point-cloud integration tests are skipped when `open3d` is not installed.
