import json
import os
import shlex
import subprocess
import tempfile

import numpy as np
import rasterio


THERMAL_NODATA = -9999.0

# DJI R-JPEGs (M2EA, M3T, H20T/H20N, M30T) keep their radiometric data in a
# proprietary segment that only DJI's Thermal SDK can decode. Point this at the
# SDK's dji_irp sample binary, or give a full command template using {input}
# and {output}; the output must be row-major float32 Celsius values.
DJI_IRP_COMMAND_ENV = 'THERMAL_DJI_IRP_COMMAND'
DJI_IRP_DEFAULT_ARGS = ['-s', '{input}', '-a', 'measure', '-o', '{output}', '--measurefmt', 'float32']
JPEG_EXTENSIONS = ('.jpg', '.jpeg', '.rjpeg')

# A radiometric TIFF should decode to plausible temperatures almost everywhere;
# anything below this is a visual export, not temperature data.
MIN_PLAUSIBLE_FRACTION = 0.9


class UnsupportedThermalImage(RuntimeError):
    pass


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


def _dji_irp_command(input_path, output_path):
    configured = (os.environ.get(DJI_IRP_COMMAND_ENV) or '').strip()
    if not configured:
        return None

    parts = shlex.split(configured)
    if not any('{input}' in part for part in parts):
        parts = parts + DJI_IRP_DEFAULT_ARGS

    return [part.replace('{input}', input_path).replace('{output}', output_path) for part in parts]


def _image_size(image_path):
    from PIL import Image

    with Image.open(image_path) as image:
        return image.size  # (width, height)


def decode_dji_rjpeg(image_path):
    """
    Decode a DJI R-JPEG through the DJI Thermal SDK's dji_irp tool.
    """
    fd, raw_path = tempfile.mkstemp(suffix='.raw')
    os.close(fd)

    try:
        command = _dji_irp_command(image_path, raw_path)
        if command is None:
            raise UnsupportedThermalImage(
                f'{os.path.basename(image_path)} is a DJI R-JPEG, which needs the DJI Thermal SDK to read '
                f'temperatures. Set {DJI_IRP_COMMAND_ENV} to the dji_irp binary, export radiometric TIFFs '
                'from DJI Thermal Analysis Tool instead, or process the thermal frames on their own with '
                'the Thermal preset.'
            )

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f'dji_irp failed for {os.path.basename(image_path)}: {result.stderr.strip() or result.stdout.strip()}')

        width, height = _image_size(image_path)
        values = np.fromfile(raw_path, dtype='<f4')
        if values.size != width * height:
            raise RuntimeError(
                f'dji_irp returned {values.size} temperature values for {os.path.basename(image_path)}, '
                f'expected {width * height} ({width}x{height}).'
            )
        celsius = values.reshape((height, width)).astype(np.float32)
    finally:
        if os.path.isfile(raw_path):
            os.remove(raw_path)

    celsius[~np.isfinite(celsius)] = THERMAL_NODATA
    profile = {'driver': 'GTiff', 'width': width, 'height': height, 'count': 1, 'dtype': 'float32'}
    return celsius, profile


def _plausible_fraction(celsius):
    valid = np.isfinite(celsius) & (celsius > -80.0) & (celsius < 250.0)
    return float(valid.sum()) / max(celsius.size, 1)


def decode_dji_tiff(image_path):
    """
    Decode a radiometric TIFF (for example a DJI Thermal Analysis Tool export):
    float values are taken as Celsius, integer values as deci/centi-Kelvin or
    deci-Celsius. Visual (multi-band or implausible) exports are refused.
    """
    with rasterio.open(image_path) as src:
        if src.count != 1:
            raise UnsupportedThermalImage(
                f'{os.path.basename(image_path)} has {src.count} bands and is not a radiometric TIFF.'
            )
        raw = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        nodata = src.nodata
        is_integer = np.issubdtype(src.dtypes[0], np.integer)

    if nodata is not None:
        raw[raw == nodata] = np.nan

    if is_integer:
        candidates = [(raw / 10.0) - 273.15, (raw / 100.0) - 273.15, raw / 10.0]
        best = max(candidates, key=_plausible_fraction)
    else:
        best = raw

    if _plausible_fraction(best) < MIN_PLAUSIBLE_FRACTION:
        raise UnsupportedThermalImage(
            f'{os.path.basename(image_path)} does not contain plausible temperature values; '
            'export a radiometric TIFF rather than a visual one.'
        )

    celsius = best.astype(np.float32)
    celsius[~np.isfinite(celsius)] = THERMAL_NODATA
    return celsius, profile


def decode_dji(image_path):
    extension = os.path.splitext(image_path)[1].lower()
    if extension in JPEG_EXTENSIONS:
        return decode_dji_rjpeg(image_path)
    return decode_dji_tiff(image_path)


def decode_radiometric(image_path, camera_type='auto'):
    metadata = read_exif_metadata(image_path, tags=['Make', 'Model', 'PlanckR1'])
    if camera_type == 'auto':
        if metadata.get('PlanckR1') not in (None, ''):
            # FLIR radiometric container, also used by the DJI Zenmuse XT.
            camera_type = 'flir'
        else:
            camera_type = detect_camera_type(image_path, metadata)

    if camera_type == 'flir':
        return decode_flir(image_path)
    if camera_type == 'dji':
        return decode_dji(image_path)

    raise ValueError(f'Unsupported camera_type: {camera_type}')
