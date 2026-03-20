# Geometry Correction — WebODM Plugin

AI-assisted geometric correction for 3D point clouds, meshes, and orthomosaics
produced by WebODM drone mapping workflows.

---

## What it does

| Output | Problem solved | Method |
|---|---|---|
| Point cloud (.laz/.ply) | Curved walls, wavy floors from SfM drift | RANSAC plane detection + orthogonal projection |
| 3D mesh (.obj) | Bulging surfaces, noisy vertices near edges | Normal clustering + vertex snapping + Laplacian smooth |
| Orthomosaic (.tif) | Skewed building edges, non-perpendicular streets | Hough line detection + homographic warp |

All corrections are **non-destructive**: original files are preserved and corrected
versions are written to `assets/geometry_correction/`.

---

## Installation

### 1. Copy plugin into WebODM

```bash
cp -r geometry_correction /path/to/WebODM/coreplugins/
```

### 2. Install Python dependencies

```bash
cd /path/to/WebODM
pip install -r coreplugins/geometry_correction/requirements.txt
```

### 3. Run Django migration

```bash
python manage.py migrate geometry_correction
```

### 4. Restart WebODM

```bash
./webodm.sh restart
```

The "⬡ Geometry Correction" button will appear on every task detail page.

---

## Usage

### Via the Web UI

1. Open any completed WebODM task
2. Click **⬡ Geometry Correction** in the task toolbar
3. Adjust parameters (or keep defaults)
4. Click **Run Correction**
5. Watch the progress bar — stats appear when done
6. Corrected files appear in the task's asset folder

### Via the REST API

```bash
# Trigger correction
curl -X POST http://localhost:8000/api/plugins/geometry_correction/correct/ \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "task_id": "your-task-uuid",
    "options": {
      "plane_threshold": 0.05,
      "correction_threshold": 0.05,
      "line_angle_tolerance": 2.0,
      "generate_mesh": true,
      "correct_orthophoto": true,
      "correct_pointcloud": true
    }
  }'

# Poll status
curl http://localhost:8000/api/plugins/geometry_correction/status/<job_id>/
```

### Via management command

```bash
python manage.py geometry_correction \
    --task-id <uuid> \
    --project-id 1 \
    --plane-threshold 0.05 \
    --line-angle-tolerance 2.0
```

---

## Configuration

All parameters can be set via environment variables (prefix `GC_`):

| Variable | Default | Description |
|---|---|---|
| `GC_PLANE_DISTANCE_THRESHOLD` | `0.05` | RANSAC inlier distance (m) |
| `GC_CORRECTION_THRESHOLD` | `0.05` | Max snap distance (m) |
| `GC_MIN_INLIER_RATIO` | `0.02` | Min plane size (fraction) |
| `GC_MAX_PLANES` | `10` | Max planes to extract |
| `GC_GENERATE_MESH` | `true` | Run Poisson re-meshing |
| `GC_MESH_DEPTH` | `9` | Poisson octree depth |
| `GC_LINE_ANGLE_TOLERANCE_DEG` | `2.0` | H/V line tolerance (°) |
| `GC_USE_HOMOGRAPHY` | `true` | Apply homographic warp |
| `GC_WEBODM_DATA_ROOT` | `/var/www/data` | WebODM data directory |

---

## Running tests

```bash
# Install test deps
pip install pytest pytest-cov

# Run all tests
python -m pytest geometry_correction/tests/ -v

# With coverage
python -m pytest geometry_correction/tests/ -v --cov=geometry_correction --cov-report=term-missing
```

---

## Output files

After a successful correction run, these files are written to
`assets/geometry_correction/` inside the task folder:

| File | Description |
|---|---|
| `odm_filterpoint_corrected.ply` | Corrected point cloud |
| `odm_mesh_corrected.obj` | Re-meshed 3D model |
| `odm_orthophoto_corrected.tif` | Corrected GeoTIFF orthomosaic |

---

## Architecture

```
geometry_correction/
├── plugin.py                   WebODM plugin entry point
├── models.py                   Django model: CorrectionJob
├── views.py                    REST API (trigger / status / list)
├── urls.py                     URL routing
├── tasks.py                    Celery async task
├── config.py                   All tunable parameters
├── algorithms/
│   ├── pointcloud.py           RANSAC + plane projection pipeline
│   ├── orthophoto.py           Hough lines + homographic correction
│   └── mesh.py                 Vertex snapping + Laplacian smoothing
├── static/geometry_correction/
│   └── main.js                 Frontend button + modal UI
├── tests/
│   ├── test_pointcloud.py      30+ unit tests for point cloud
│   └── test_orthophoto.py      25+ unit tests for orthophoto
├── migrations/
│   └── 0001_initial.py         Django DB migration
└── requirements.txt            Python dependencies
```
