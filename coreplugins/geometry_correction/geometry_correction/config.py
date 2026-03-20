"""
config.py — All tunable parameters for the geometry_correction plugin.

Override any value via environment variables prefixed with GC_:
  GC_PLANE_DISTANCE_THRESHOLD=0.03 -> PLANE_DISTANCE_THRESHOLD = 0.03
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
    val = os.environ.get("GC_" + key, "").lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


# Point cloud parameters
PLANE_DISTANCE_THRESHOLD = _env_float("PLANE_DISTANCE_THRESHOLD", 0.05)
CORRECTION_THRESHOLD = _env_float("CORRECTION_THRESHOLD", 0.05)
MIN_INLIER_RATIO = _env_float("MIN_INLIER_RATIO", 0.02)
MAX_PLANES = _env_int("MAX_PLANES", 10)
GENERATE_MESH = _env_bool("GENERATE_MESH", True)
MESH_DEPTH = _env_int("MESH_DEPTH", 9)

# Orthophoto parameters
LINE_ANGLE_TOLERANCE_DEG = _env_float("LINE_ANGLE_TOLERANCE_DEG", 2.0)
CANNY_LOW = _env_int("CANNY_LOW", 50)
CANNY_HIGH = _env_int("CANNY_HIGH", 150)
HOUGH_THRESHOLD = _env_int("HOUGH_THRESHOLD", 80)
MIN_LINE_LENGTH = _env_int("MIN_LINE_LENGTH", 100)
USE_HOMOGRAPHY = _env_bool("USE_HOMOGRAPHY", True)
USE_ROTATION = _env_bool("USE_ROTATION", True)

# Mesh direct correction parameters
MESH_SNAP_THRESHOLD = _env_float("MESH_SNAP_THRESHOLD", 0.05)
MESH_SMOOTHING_ITERATIONS = _env_int("MESH_SMOOTHING_ITERATIONS", 3)

# WebODM integration
WEBODM_DATA_ROOT = os.environ.get("WEBODM_DATA_ROOT", "/var/www/data")
CELERY_QUEUE = os.environ.get("GC_CELERY_QUEUE", "celery")
