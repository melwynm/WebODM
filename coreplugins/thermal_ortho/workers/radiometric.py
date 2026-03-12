import json
import os
import subprocess
import tempfile

import numpy as np
import rasterio


THERMAL_NODATA = -9999.0


def _run_exiftool(args, image_path=None):
    cmd = ['exiftool']
    cmd.extend(args)
    if image_path is not None:
        cmd.append(image_path)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'exiftool failed for {image_path}: {result.stderr.strip()}')
    return result.stdout


def read_exif_metadata(image_path, tags=None):
    args = ['-json', '-n']
    if tags:
        for tag in tags:
            args.append(f'-{tag}')
    else:
        args.append('-all')

    output = _run_exiftool(args, image_path=image_path)
    data = json.loads(output)
    return data[0] if data else {}


def _float_value(value, default=None):
    if value in (None, ''):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(str(value).split(' ')[0])
        except (TypeError, ValueError):
            return default


def _read_single_band_raster(image_path):
    with rasterio.open(image_path) as src:
        array = src.read(1).astype(np.float32)
        profile = src.profile.copy()
    return array, profile


def _extract_embedded_raw(image_path):
    fd, tmp_path = tempfile.mkstemp(suffix='.tiff')
    os.close(fd)

    with open(tmp_path, 'wb') as dst:
        result = subprocess.run(['exiftool', '-b', '-RawThermalImage', image_path], stdout=dst, stderr=subprocess.PIPE)

    if result.returncode != 0 or os.path.getsize(tmp_path) == 0:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return None

    return tmp_path


def detect_camera_type(image_path, metadata=None):
    metadata = metadata or read_exif_metadata(image_path, tags=['Make', 'Model'])
    make = str(metadata.get('Make', '')).upper()
    model = str(metadata.get('Model', '')).upper()
    name = os.path.basename(image_path).upper()

    if 'FLIR' in make or 'FLIR' in model:
        return 'flir'
    if 'DJI' in make or 'DJI' in model or any(token in model for token in ('M3T', 'H20T', 'M2EA')):
        return 'dji'
    if any(token in name for token in ('_T.', '_T_', 'THERMAL', 'RJPEG', 'R.JPEG')):
        return 'dji'
    return 'dji'


def decode_flir(image_path):
    metadata = read_exif_metadata(image_path, tags=['PlanckR1', 'PlanckB', 'PlanckF', 'PlanckO', 'PlanckR2'])
    r1 = _float_value(metadata.get('PlanckR1') or metadata.get('Planck R1'))
    r2 = _float_value(metadata.get('PlanckR2') or metadata.get('Planck R2'))
    b = _float_value(metadata.get('PlanckB') or metadata.get('Planck B'))
    f = _float_value(metadata.get('PlanckF') or metadata.get('Planck F'), 1.0)
    o = _float_value(metadata.get('PlanckO') or metadata.get('Planck O'), 0.0)

    if None in (r1, r2, b):
        raise ValueError(f'Missing FLIR Planck constants for {image_path}')

    raw_path = _extract_embedded_raw(image_path) if os.path.splitext(image_path)[1].lower() in ('.jpg', '.jpeg') else None
    source_path = raw_path or image_path

    try:
        raw, profile = _read_single_band_raster(source_path)
    finally:
        if raw_path and os.path.isfile(raw_path):
            os.remove(raw_path)

    with np.errstate(divide='ignore', invalid='ignore'):
        kelvin = b / np.log((r1 / (r2 * (raw + o))) + f)
    celsius = (kelvin - 273.15).astype(np.float32)
    celsius[~np.isfinite(celsius)] = THERMAL_NODATA
    return celsius, profile


def decode_dji(image_path):
    raw_path = _extract_embedded_raw(image_path) if os.path.splitext(image_path)[1].lower() in ('.jpg', '.jpeg') else None
    source_path = raw_path or image_path

    try:
        raw, profile = _read_single_band_raster(source_path)
    finally:
        if raw_path and os.path.isfile(raw_path):
            os.remove(raw_path)

    candidates = [
        (raw / 10.0) - 273.15,
        (raw / 100.0) - 273.15,
        raw / 10.0,
    ]

    best = candidates[0]
    best_score = -1
    for candidate in candidates:
        valid = np.isfinite(candidate) & (candidate > -80.0) & (candidate < 250.0)
        score = int(valid.sum())
        if score > best_score:
            best = candidate
            best_score = score

    celsius = best.astype(np.float32)
    celsius[~np.isfinite(celsius)] = THERMAL_NODATA
    return celsius, profile


def decode_radiometric(image_path, camera_type='auto'):
    metadata = read_exif_metadata(image_path, tags=['Make', 'Model'])
    if camera_type == 'auto':
        camera_type = detect_camera_type(image_path, metadata)

    if camera_type == 'flir':
        return decode_flir(image_path)
    if camera_type == 'dji':
        return decode_dji(image_path)

    raise ValueError(f'Unsupported camera_type: {camera_type}')
