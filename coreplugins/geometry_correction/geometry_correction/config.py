"""
Configuration values for the geometry_correction plugin.

All values can be overridden with environment variables prefixed with ``GC_``.
"""

import os


def _env_float(key, default):
    try:
        return float(os.environ.get("GC_" + key, ""))
    except (ValueError, TypeError):
        return default


def _env_int(key, default):
    try:
        return int(os.environ.get("GC_" + key, ""))
    except (ValueError, TypeError):
        return default


def _env_bool(key, default):
    val = os.environ.get("GC_" + key, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


OUTPUT_DIRNAME = os.environ.get("GC_OUTPUT_DIRNAME", "geometry_correction")

# Point cloud and plane detection parameters
PLANE_DISTANCE_THRESHOLD = _env_float("PLANE_DISTANCE_THRESHOLD", 0.05)
SNAP_DEVIATION_THRESHOLD = _env_float("SNAP_DEVIATION_THRESHOLD", 0.05)
CORRECTION_THRESHOLD = _env_float("CORRECTION_THRESHOLD", SNAP_DEVIATION_THRESHOLD)
PLANE_RANSAC_N = _env_int("PLANE_RANSAC_N", 3)
PLANE_NUM_ITERATIONS = _env_int("PLANE_NUM_ITERATIONS", 1000)
PLANE_MIN_INLIERS = _env_int("PLANE_MIN_INLIERS", 100)
MIN_INLIER_RATIO = _env_float("MIN_INLIER_RATIO", 0.02)
MAX_PLANES = _env_int("MAX_PLANES", 20)
USE_SEMANTIC_PROFILES = _env_bool("USE_SEMANTIC_PROFILES", True)

# Point cloud smoothing and meshing
PLANE_SMOOTHING_NEIGHBORS = _env_int("PLANE_SMOOTHING_NEIGHBORS", 6)
POISSON_DEPTH = _env_int("POISSON_DEPTH", 9)
POISSON_MIN_DENSITY_QUANTILE = _env_float("POISSON_MIN_DENSITY_QUANTILE", 0.02)
GENERATE_MESH = _env_bool("GENERATE_MESH", True)
MESH_DEPTH = POISSON_DEPTH
MESH_SNAP_THRESHOLD = _env_float("MESH_SNAP_THRESHOLD", SNAP_DEVIATION_THRESHOLD)
MESH_SMOOTHING_ITERATIONS = _env_int("MESH_SMOOTHING_ITERATIONS", 3)

# Orthophoto parameters
LINE_ANGLE_TOLERANCE = _env_float("LINE_ANGLE_TOLERANCE", 2.0)
LINE_ANGLE_TOLERANCE_DEG = LINE_ANGLE_TOLERANCE
CANNY_LOW = _env_int("CANNY_LOW", 50)
CANNY_HIGH = _env_int("CANNY_HIGH", 150)
HOUGH_RHO = _env_float("HOUGH_RHO", 1.0)
HOUGH_THETA_DEGREES = _env_float("HOUGH_THETA_DEGREES", 1.0)
HOUGH_THRESHOLD = _env_int("HOUGH_THRESHOLD", 80)
HOUGH_MIN_LINE_LENGTH = _env_int("HOUGH_MIN_LINE_LENGTH", 100)
HOUGH_MAX_LINE_GAP = _env_int("HOUGH_MAX_LINE_GAP", 10)
MIN_LINE_LENGTH = HOUGH_MIN_LINE_LENGTH
USE_HOMOGRAPHY = _env_bool("USE_HOMOGRAPHY", True)
USE_ROTATION = _env_bool("USE_ROTATION", True)
GENERATE_CONFIDENCE_MAP = _env_bool("GENERATE_CONFIDENCE_MAP", True)

# Webhooks
WEBHOOK_TIMEOUT_S = _env_int("WEBHOOK_TIMEOUT_S", 10)

# WebODM integration
WEBODM_DATA_ROOT = os.environ.get("WEBODM_DATA_ROOT", "/var/www/data")
CELERY_QUEUE = os.environ.get("GC_CELERY_QUEUE", "celery")
