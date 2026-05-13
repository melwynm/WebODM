import os
import shutil
import subprocess
import zipfile

from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions


TEXTURED_MODEL_GLB_ASSET = 'textured_model.glb'
TEXTURED_MODEL_FBX_PACKAGE_ASSET = 'textured_model.fbx.zip'
TEXTURED_MODEL_DERIVED_ASSETS = (
    TEXTURED_MODEL_GLB_ASSET,
    TEXTURED_MODEL_FBX_PACKAGE_ASSET,
)

TEXTURED_MODEL_DIR = 'odm_texturing'
NATIVE_GLB = 'odm_textured_model_geo.glb'
SOURCE_MODELS = (
    ('odm_textured_model_geo.obj', 'odm_textured_model_geo.mtl'),
    ('odm_textured_model.obj', 'odm_textured_model.mtl'),
)

TEXTURE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')
MTL_TEXTURE_KEYS = {
    'map_ka',
    'map_kd',
    'map_ks',
    'map_ke',
    'map_ns',
    'map_d',
    'map_bump',
    'bump',
    'disp',
    'decal',
}


def _assimp_bin():
    return shutil.which('assimp')


def _native_glb_path(task):
    return task.assets_path(TEXTURED_MODEL_DIR, NATIVE_GLB)


def _find_source_model(task):
    for obj_name, mtl_name in SOURCE_MODELS:
        obj_path = task.assets_path(TEXTURED_MODEL_DIR, obj_name)
        if os.path.isfile(obj_path):
            mtl_path = task.assets_path(TEXTURED_MODEL_DIR, mtl_name)
            return obj_path, mtl_path if os.path.isfile(mtl_path) else None
    return None, None


def _cache_dir(task):
    export_dir = os.path.join(task.get_task_assets_cache(), 'textured_model_exports')
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def _is_up_to_date(output_path, input_paths):
    if not os.path.isfile(output_path):
        return False
    output_mtime = os.path.getmtime(output_path)
    return all(os.path.getmtime(path) <= output_mtime for path in input_paths if os.path.isfile(path))


def _run_assimp_export(source_obj, output_path, assimp_format):
    assimp = _assimp_bin()
    if assimp is None:
        raise exceptions.ValidationError(_('assimp is required to export textured models.'))

    source_dir = os.path.dirname(source_obj)
    output_root, output_ext = os.path.splitext(output_path)
    tmp_output = '{}.tmp{}'.format(output_root, output_ext)
    if os.path.exists(tmp_output):
        os.remove(tmp_output)

    args = [
        assimp,
        'export',
        os.path.basename(source_obj),
        tmp_output,
        '-f',
        assimp_format,
    ]
    process = subprocess.Popen(
        args,
        cwd=source_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = process.communicate()
    if process.returncode != 0:
        if os.path.exists(tmp_output):
            os.remove(tmp_output)
        message = err.decode('utf-8').strip() or out.decode('utf-8').strip() or 'assimp export failed'
        raise exceptions.ValidationError(message)

    os.replace(tmp_output, output_path)
    return output_path


def _parse_mtl_texture_paths(mtl_path):
    if not mtl_path or not os.path.isfile(mtl_path):
        return []

    texture_paths = []
    mtl_dir = os.path.dirname(mtl_path)
    with open(mtl_path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            clean = line.split('#', 1)[0].strip()
            if not clean:
                continue
            parts = clean.split()
            if len(parts) < 2 or parts[0].lower() not in MTL_TEXTURE_KEYS:
                continue
            texture_name = parts[-1].strip('"').strip("'")
            texture_path = os.path.normpath(os.path.join(mtl_dir, texture_name))
            if os.path.isfile(texture_path):
                texture_paths.append(texture_path)

    return texture_paths


def _texture_files_for_package(source_obj, mtl_path):
    texture_paths = _parse_mtl_texture_paths(mtl_path)
    if texture_paths:
        return sorted(set(texture_paths))

    source_dir = os.path.dirname(source_obj)
    return sorted(
        os.path.join(source_dir, filename)
        for filename in os.listdir(source_dir)
        if filename.lower().endswith(TEXTURE_EXTENSIONS)
    )


def is_textured_model_export_available(task, asset):
    if asset == TEXTURED_MODEL_GLB_ASSET and os.path.isfile(_native_glb_path(task)):
        return True

    if asset not in TEXTURED_MODEL_DERIVED_ASSETS:
        return False

    source_obj, _mtl_path = _find_source_model(task)
    return source_obj is not None and _assimp_bin() is not None


def get_textured_model_export_path(task, asset):
    native_glb = _native_glb_path(task)
    if asset == TEXTURED_MODEL_GLB_ASSET and os.path.isfile(native_glb):
        return native_glb

    source_obj, mtl_path = _find_source_model(task)
    if source_obj is None:
        raise FileNotFoundError('Textured OBJ model is not available')
    if _assimp_bin() is None:
        raise FileNotFoundError('assimp is not available')

    export_dir = _cache_dir(task)
    source_inputs = [source_obj]
    if mtl_path:
        source_inputs.append(mtl_path)

    if asset == TEXTURED_MODEL_GLB_ASSET:
        output_glb = os.path.join(export_dir, 'textured_model.glb')
        if not _is_up_to_date(output_glb, source_inputs):
            _run_assimp_export(source_obj, output_glb, 'glb2')
        return output_glb

    if asset == TEXTURED_MODEL_FBX_PACKAGE_ASSET:
        output_fbx = os.path.join(export_dir, 'textured_model.fbx')
        textures = _texture_files_for_package(source_obj, mtl_path)
        package_inputs = source_inputs + textures
        if not _is_up_to_date(output_fbx, package_inputs):
            _run_assimp_export(source_obj, output_fbx, 'fbx')

        output_zip = os.path.join(export_dir, 'textured_model_fbx.zip')
        package_inputs = [output_fbx] + textures
        if not _is_up_to_date(output_zip, package_inputs):
            tmp_zip = output_zip + '.tmp'
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
            with zipfile.ZipFile(tmp_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(output_fbx, 'textured_model.fbx')
                for texture_path in textures:
                    archive.write(texture_path, os.path.basename(texture_path))
            os.replace(tmp_zip, output_zip)

        return output_zip

    raise FileNotFoundError('{} is not a valid textured model export'.format(asset))
