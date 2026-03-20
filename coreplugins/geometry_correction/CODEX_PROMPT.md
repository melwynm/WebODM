# CODEX PROMPT — Geometry Correction Plugin: Add Features & Run Tests
# Copy everything below this line and paste it into Codex / Claude / GPT-4o

---

You are an expert Python and Django developer working on an open-source
WebODM plugin called `geometry_correction`. The plugin already exists and
is fully implemented. Your job is to:

  1. Run the existing test suite and fix any failures
  2. Add the new features described below
  3. Write tests for every new feature
  4. Verify the full test suite passes before finishing

---

## REPOSITORY STRUCTURE

The plugin lives at: `coreplugins/geometry_correction/` inside a WebODM repo.

```
geometry_correction/
├── plugin.py
├── models.py
├── views.py
├── urls.py
├── tasks.py
├── config.py
├── requirements.txt
├── algorithms/
│   ├── __init__.py
│   ├── pointcloud.py      (RANSAC plane detection + projection)
│   ├── orthophoto.py      (Hough line detection + homographic warp)
│   └── mesh.py            (vertex snapping + Laplacian smooth)
├── static/geometry_correction/
│   └── main.js
├── tests/
│   ├── __init__.py
│   ├── test_pointcloud.py
│   └── test_orthophoto.py
└── migrations/
    └── 0001_initial.py
```

---

## STEP 1 — RUN EXISTING TESTS AND FIX FAILURES

```bash
cd /path/to/WebODM
pip install open3d laspy lazrs-python rasterio opencv-python scipy pytest pytest-cov
python -m pytest coreplugins/geometry_correction/tests/ -v 2>&1 | tee test_output.txt
```

Read `test_output.txt`. For every FAILED or ERROR test:
- Diagnose the root cause (do NOT just skip the test)
- Fix the bug in the implementation file (not the test)
- Re-run that specific test to confirm it passes
- Only move to Step 2 once ALL tests pass

---

## STEP 2 — ADD THESE NEW FEATURES

Implement each feature below as a new module or extension to an existing one.
Follow the same coding style: type hints, dataclasses for stats, logging,
try/except with error accumulation, non-destructive outputs.

---

### Feature A: Semantic-Aware Plane Classification
**File:** `algorithms/semantic.py`

Add semantic labels to detected planes so the correction logic can be smarter
about which planes to snap (e.g. be more aggressive on walls, gentler on organic
terrain).

```python
class PlaneClass(Enum):
    WALL       = "wall"        # near-vertical, man-made
    FLOOR      = "floor"       # near-horizontal, ground level
    ROOF       = "roof"        # near-horizontal, elevated
    RAMP       = "ramp"        # diagonal, 5-45 degrees
    UNKNOWN    = "unknown"

@dataclass
class ClassifiedPlane:
    plane: PlaneResult          # existing PlaneResult dataclass
    label: PlaneClass
    confidence: float           # 0.0–1.0

def classify_planes(planes: List[PlaneResult], point_cloud_centroid: np.ndarray) -> List[ClassifiedPlane]:
    """
    Classify each detected plane using:
    - Normal vector direction (vertical vs horizontal)
    - Centroid height relative to the cloud's centroid
    - Inlier bounding box aspect ratio (walls are tall+narrow, floors are wide+flat)

    Rules:
    - |normal.z| > 0.85 AND centroid_z < cloud_centroid_z + 0.3m  -> FLOOR
    - |normal.z| > 0.85 AND centroid_z > cloud_centroid_z + 1.5m  -> ROOF
    - |normal.z| < 0.3                                             -> WALL
    - 0.3 <= |normal.z| < 0.85                                     -> RAMP
    - confidence = how well the normal matches the rule threshold
    """
```

Write 8+ unit tests in `tests/test_semantic.py`:
- Test each class is assigned correctly for synthetic planes with known normals
- Test confidence is higher when the normal aligns perfectly with the rule
- Test that a wall and a floor in the same cloud get different labels
- Test edge cases: normals exactly on the boundary between categories

---

### Feature B: Per-Class Correction Profiles
**File:** `algorithms/correction_profiles.py`

Different surface types need different correction aggressiveness.

```python
@dataclass
class CorrectionProfile:
    snap_threshold_m: float        # max distance to snap a point onto the plane
    ransac_distance_m: float       # RANSAC inlier threshold for this class
    smoothing_iterations: int      # Laplacian smoothing passes after correction
    enabled: bool                  # can disable correction for a class entirely

DEFAULT_PROFILES = {
    PlaneClass.WALL:    CorrectionProfile(snap_threshold_m=0.04, ransac_distance_m=0.03, smoothing_iterations=2, enabled=True),
    PlaneClass.FLOOR:   CorrectionProfile(snap_threshold_m=0.06, ransac_distance_m=0.05, smoothing_iterations=1, enabled=True),
    PlaneClass.ROOF:    CorrectionProfile(snap_threshold_m=0.05, ransac_distance_m=0.04, smoothing_iterations=2, enabled=True),
    PlaneClass.RAMP:    CorrectionProfile(snap_threshold_m=0.08, ransac_distance_m=0.06, smoothing_iterations=3, enabled=True),
    PlaneClass.UNKNOWN: CorrectionProfile(snap_threshold_m=0.05, ransac_distance_m=0.05, smoothing_iterations=1, enabled=False),
}

def get_profile(label: PlaneClass, overrides: dict = None) -> CorrectionProfile:
    """Return the correction profile for a class, with optional user overrides."""
```

Update `algorithms/pointcloud.py`:
- Add a `use_semantic_profiles: bool = True` parameter to `run_pointcloud_correction()`
- When True, classify each detected plane and apply its profile's thresholds
- When False, use the existing single global threshold (backwards compatible)

Write 6+ unit tests in `tests/test_correction_profiles.py`:
- Test that WALL profile has tighter threshold than FLOOR
- Test that UNKNOWN class is disabled by default
- Test that overrides correctly replace default values
- Test end-to-end: a cloud with a clear wall and floor uses different thresholds for each

---

### Feature C: Confidence Heatmap for Orthomosaic
**File:** `algorithms/confidence_map.py`

Generate a single-band GeoTIFF "confidence map" showing which pixels of the
orthomosaic were corrected and by how much. This helps users see exactly what
the plugin changed.

```python
def generate_confidence_map(
    original_bgr: np.ndarray,
    corrected_bgr: np.ndarray,
    profile: dict,                  # rasterio profile from the original GeoTIFF
    output_path: str,
) -> str:
    """
    Compute per-pixel difference magnitude between original and corrected image.
    Normalise to 0-255 uint8 (0 = unchanged, 255 = max change).
    Save as single-band GeoTIFF with the same CRS/transform as the source.
    Returns the output path.
    """
```

Also add:
```python
def compute_correction_coverage_pct(confidence_map: np.ndarray, threshold: int = 5) -> float:
    """Return percentage of pixels that changed by more than `threshold` intensity."""
```

Update `algorithms/orthophoto.py`:
- Add `generate_confidence_map: bool = True` parameter to `run_orthophoto_correction()`
- When True, generate and save the map; add its path to `OrthoCorrectionStats`
- Add `confidence_map_path: str = ""` and `coverage_pct: float = 0.0` to `OrthoCorrectionStats`

Write 8+ unit tests in `tests/test_confidence_map.py`:
- Test that an unchanged image produces an all-zero confidence map
- Test that a completely shifted image produces a high-value confidence map
- Test that `compute_correction_coverage_pct` returns 0.0 for identical images
- Test that `compute_correction_coverage_pct` returns ~100.0 when all pixels differ
- Test that the output GeoTIFF has the correct CRS and transform (use rasterio to verify)
- Test that the map is single-band uint8
- Test with different threshold values
- Test that the coverage_pct in OrthoCorrectionStats is populated correctly

---

### Feature D: Webhook Notification on Completion
**File:** `algorithms/webhook.py`

Notify an external URL when a correction job finishes (success or failure).

```python
import requests
from dataclasses import dataclass
from typing import Optional

@dataclass
class WebhookConfig:
    url: str
    secret: str = ""            # HMAC-SHA256 signing secret (empty = no signing)
    timeout_s: int = 10

def send_completion_webhook(
    config: WebhookConfig,
    job_id: str,
    status: str,                # "COMPLETED" or "FAILED"
    result: dict,
    error: Optional[str] = None,
) -> bool:
    """
    POST a JSON payload to config.url.
    Payload: { job_id, status, result, error, timestamp }
    If config.secret is set, add header X-GC-Signature: sha256=<hmac>
    Returns True on HTTP 2xx, False otherwise.
    Never raises — catch all exceptions and log them.
    """
```

Update `tasks.py`:
- Read webhook URL from `options.get("webhook_url", "")` and `options.get("webhook_secret", "")`
- Call `send_completion_webhook()` after `job.mark_completed()` or `job.mark_failed()`

Update `views.py`:
- Accept `webhook_url` and `webhook_secret` in the POST body options

Write 8+ unit tests in `tests/test_webhook.py` using `unittest.mock`:
- Test that a 200 response returns True
- Test that a 4xx response returns False
- Test that a network exception returns False (never raises)
- Test HMAC signature is present when secret is non-empty
- Test HMAC signature is absent when secret is empty
- Test that the HMAC signature is valid (verify it in the test)
- Test that the payload contains all required fields
- Test that `send_completion_webhook` is called from the Celery task on completion
- Test that it is also called on failure

---

## STEP 3 — VERIFY COMPLETE TEST SUITE

After implementing all features and their tests:

```bash
python -m pytest coreplugins/geometry_correction/tests/ -v \
    --cov=coreplugins/geometry_correction \
    --cov-report=term-missing \
    --cov-report=html:coverage_html \
    2>&1 | tee final_test_output.txt
```

Requirements before declaring success:
- ALL tests pass (0 failures, 0 errors)
- Total test count is >= 65 (existing ~55 + new ~25+)
- Coverage for `algorithms/` is >= 80%
- No test uses `pytest.skip()` to hide a bug
- Print a final summary table: feature | tests added | coverage %

---

## CODING STANDARDS TO FOLLOW

- Python 3.8+ compatible (no walrus operator, no `match` statements)
- All functions have type hints and a docstring
- Use `@dataclass` for all result/stats objects
- All I/O errors caught and added to a `.errors: List[str]` field
- Logging via `logger = logging.getLogger(__name__)`
- No hardcoded paths — use `config.py` constants or function parameters
- Tests use only `pytest`, `numpy`, `unittest.mock` — no heavy fixtures
- Test functions named `test_<what>_<expected_outcome>` pattern
- Each test file has a module-level docstring explaining what it tests

---

## ACCEPTANCE CRITERIA

You are done when:
[ ] `python -m pytest geometry_correction/tests/ -v` shows ALL GREEN
[ ] All 4 new features are implemented with their modules
[ ] `algorithms/pointcloud.py` uses semantic profiles when enabled
[ ] `algorithms/orthophoto.py` generates confidence maps when enabled
[ ] `tasks.py` fires webhooks on completion and failure
[ ] No existing public API is broken (backwards compatible)
[ ] README.md is updated with the 4 new features documented
