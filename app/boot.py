import os
import sys

import kombu
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User, Group
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.core.files import File
from django.db.utils import ProgrammingError
from guardian.shortcuts import assign_perm

from worker import tasks as worker_tasks
from app.models import Preset
from app.models import Theme
from app.models.theme import ACCESSIBLE_THEME_DEFAULTS
from app.plugins import init_plugins
from nodeodm.models import ProcessingNode
# noinspection PyUnresolvedReferencesapp/boot.py#L20
from webodm.settings import MEDIA_ROOT
from . import signals
import logging
from .models import Task, Setting
from webodm import settings
from webodm.wsgi import booted

THEME_CONTRAST_MIN = 4.5
THEME_COLOR_FIELDS = (
    "primary",
    "secondary",
    "tertiary",
    "button_primary",
    "button_default",
    "button_danger",
    "header_background",
    "header_primary",
    "border",
    "highlight",
    "dialog_warning",
    "failed",
    "success",
)


def _hex_to_rgb(color):
    if not color:
        return None

    c = color.strip()
    if c.startswith("#"):
        c = c[1:]

    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)

    if len(c) != 6:
        return None

    try:
        return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None


def _linearize(channel):
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def _contrast_ratio(color_a, color_b):
    rgb_a = _hex_to_rgb(color_a)
    rgb_b = _hex_to_rgb(color_b)
    if rgb_a is None or rgb_b is None:
        return 0.0

    lum_a = 0.2126 * _linearize(rgb_a[0]) + 0.7152 * _linearize(rgb_a[1]) + 0.0722 * _linearize(rgb_a[2])
    lum_b = 0.2126 * _linearize(rgb_b[0]) + 0.7152 * _linearize(rgb_b[1]) + 0.0722 * _linearize(rgb_b[2])

    lighter = max(lum_a, lum_b)
    darker = min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def _theme_has_good_contrast(theme):
    pairs = (
        (theme.primary, theme.secondary),
        (theme.header_primary, theme.header_background),
        (theme.secondary, theme.button_primary),
        (theme.secondary, theme.button_default),
        (theme.secondary, theme.button_danger),
    )

    return all(_contrast_ratio(fg, bg) >= THEME_CONTRAST_MIN for fg, bg in pairs)


def _apply_accessible_defaults(theme):
    for field in THEME_COLOR_FIELDS:
        setattr(theme, field, ACCESSIBLE_THEME_DEFAULTS[field])


def boot():
    # booted is a shared memory variable to keep track of boot status
    # as multiple gunicorn workers could trigger the boot sequence twice
    if (not settings.DEBUG and booted.value) or settings.MIGRATING or settings.FLUSHING: return

    booted.value = True
    logger = logging.getLogger('app.logger')

    logger.info("Booting WebODM {}".format(settings.VERSION))

    if settings.DEBUG:
        logger.warning("Debug mode is ON (for development this is OK)")

    # Silence django's "Warning: Session data corrupted" messages
    session_logger = logging.getLogger("django.SuspiciousOperation.SuspiciousSession")
    session_logger.disabled = True

    # Make sure our app/media/tmp folder exists
    if not os.path.exists(settings.MEDIA_TMP):
        os.makedirs(settings.MEDIA_TMP)

    # Check default group
    try:
        default_group, created = Group.objects.get_or_create(name='Default')
        if created:
            logger.info("Created default group")

            # Assign viewprocessing node object permission to default processing node (if present)
            # Otherwise non-root users will not be able to process
            try:
                pnode = ProcessingNode.objects.get(hostname="node-odm-1")
                assign_perm('view_processingnode', default_group, pnode)
                logger.info("Added view_processingnode permissions to default group")
            except ObjectDoesNotExist:
                pass


        # Add default permissions (view_project, change_project, delete_project, etc.)
        for permission in ('_project', '_task', '_preset'):
            default_group.permissions.add(
                *list(Permission.objects.filter(codename__endswith=permission))
            )

        # Add permission to view processing nodes
        default_group.permissions.add(Permission.objects.get(codename="view_processingnode"))

        add_default_presets()

        # Add settings
        default_theme, created = Theme.objects.get_or_create(name='Default')
        default_theme_updated = False

        if created:
            logger.info("Created default theme")
            _apply_accessible_defaults(default_theme)
            default_theme_updated = True
        elif not _theme_has_good_contrast(default_theme):
            logger.warning("Default theme had insufficient contrast, resetting to accessible defaults")
            _apply_accessible_defaults(default_theme)
            default_theme_updated = True

        if settings.DEFAULT_THEME_CSS and default_theme.css == "":
            default_theme.css = settings.DEFAULT_THEME_CSS
            default_theme_updated = True

        if default_theme_updated:
            default_theme.save()

        if Setting.objects.all().count() == 0:
            s = Setting.objects.create(
                    app_name=settings.APP_NAME,
                    theme=default_theme)
            s.app_logo.save(os.path.basename(settings.APP_DEFAULT_LOGO), File(open(settings.APP_DEFAULT_LOGO, 'rb')))

            logger.info("Created settings")
        else:
            app_settings = Setting.objects.select_related('theme').first()
            if app_settings is not None and (app_settings.theme is None or not _theme_has_good_contrast(app_settings.theme)):
                app_settings.theme = default_theme
                app_settings.save(update_fields=['theme'])
                logger.info("Updated active theme to high-contrast default")

        init_plugins()

        if not settings.TESTING:
            try:
                worker_tasks.update_nodes_info.delay()
            except kombu.exceptions.OperationalError as e:
                logger.error("Cannot connect to celery broker at {}. Make sure that your redis-server is running at that address: {}".format(settings.CELERY_BROKER_URL, str(e)))


    except ProgrammingError:
        logger.warning("Could not touch the database. If running a migration, this is expected.")


def add_default_presets():
    try:
        Preset.objects.update_or_create(name='Multispectral', system=True,
                                        defaults={'description': 'Calibrated multispectral processing for reflectance-aware drone imagery.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'radiometric-calibration', 'value': 'camera'}]})
        Preset.objects.update_or_create(name='Thermal', system=True,
                                        defaults={'description': 'Thermal orthomosaic workflow with radiometric calibration and high quality point cloud settings.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'radiometric-calibration', 'value': 'camera'},
                                                              {'name': 'texturing-skip-global-seam-leveling', 'value': True},
                                                              {'name': 'pc-quality', 'value': 'high'},
                                                              {'name': 'dsm', 'value': True},
                                                              {'name': 'orthophoto-compression', 'value': 'DEFLATE'},
                                                              {'name': 'build-overviews', 'value': True},
                                                              {'name': 'cog', 'value': True}]})
        Preset.objects.update_or_create(name='DJI Drone', system=True,
                                        defaults={'description': 'Balanced DJI workflow with stronger feature matching, DSM output, and web map overviews.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'sfm-algorithm', 'value': 'triangulation'},
                                                              {'name': 'matcher-type', 'value': 'flann'},
                                                              {'name': 'matcher-neighbors', 'value': 8},
                                                              {'name': 'feature-quality', 'value': 'ultra'},
                                                              {'name': 'min-num-features', 'value': '18000'},
                                                              {'name': 'pc-quality', 'value': 'high'},
                                                              {'name': 'dsm', 'value': True},
                                                              {'name': 'use-3dmesh', 'value': True},
                                                              {'name': 'mesh-octree-depth', 'value': '12'},
                                                              {'name': 'mesh-size', 'value': '300000'},
                                                              {'name': 'orthophoto-compression', 'value': 'DEFLATE'},
                                                              {'name': 'build-overviews', 'value': True},
                                                              {'name': 'cog', 'value': True}]})
        Preset.objects.update_or_create(name='Architecture CAD Orthomosaic', system=True,
                                        defaults={'description': 'High-resolution orthomosaic workflow for CAD/design overlay comparison, construction progress review, DSM/DTM deltas, and client reporting.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'sfm-algorithm', 'value': 'triangulation'},
                                                              {'name': 'matcher-type', 'value': 'flann'},
                                                              {'name': 'matcher-neighbors', 'value': 8},
                                                              {'name': 'feature-quality', 'value': 'ultra'},
                                                              {'name': 'min-num-features', 'value': '22000'},
                                                              {'name': 'pc-quality', 'value': 'high'},
                                                              {'name': 'dsm', 'value': True},
                                                              {'name': 'dtm', 'value': True},
                                                              {'name': 'dem-resolution', 'value': '2.0'},
                                                              {'name': 'orthophoto-resolution', 'value': '1.5'},
                                                              {'name': 'orthophoto-compression', 'value': 'DEFLATE'},
                                                              {'name': 'build-overviews', 'value': True},
                                                              {'name': 'cog', 'value': True}]})
        Preset.objects.update_or_create(name='Agriculture Field Analysis', system=True,
                                        defaults={'description': 'Field analysis orthomosaic workflow with radiometric calibration, plant-health formulas, DSM output, and COG exports.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'radiometric-calibration', 'value': 'camera'},
                                                              {'name': 'sfm-algorithm', 'value': 'planar'},
                                                              {'name': 'matcher-neighbors', 'value': 4},
                                                              {'name': 'feature-quality', 'value': 'high'},
                                                              {'name': 'dsm', 'value': True},
                                                              {'name': 'dem-resolution', 'value': '5.0'},
                                                              {'name': 'orthophoto-resolution', 'value': '3.0'},
                                                              {'name': 'orthophoto-compression', 'value': 'DEFLATE'},
                                                              {'name': 'build-overviews', 'value': True},
                                                              {'name': 'cog', 'value': True}]})
        Preset.objects.update_or_create(name='Solar Panel Inspection', system=True,
                                        defaults={'description': 'High-detail orthomosaic workflow for solar farm inspection, panel issue mapping, thermal follow-up, and client review.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'sfm-algorithm', 'value': 'triangulation'},
                                                              {'name': 'matcher-type', 'value': 'flann'},
                                                              {'name': 'matcher-neighbors', 'value': 8},
                                                              {'name': 'feature-quality', 'value': 'ultra'},
                                                              {'name': 'min-num-features', 'value': '25000'},
                                                              {'name': 'pc-quality', 'value': 'high'},
                                                              {'name': 'dsm', 'value': True},
                                                              {'name': 'dem-resolution', 'value': '1.0'},
                                                              {'name': 'orthophoto-resolution', 'value': '1.0'},
                                                              {'name': 'texturing-skip-global-seam-leveling', 'value': True},
                                                              {'name': 'orthophoto-compression', 'value': 'DEFLATE'},
                                                              {'name': 'build-overviews', 'value': True},
                                                              {'name': 'cog', 'value': True}]})
        Preset.objects.update_or_create(name='Commercial 3D Model', system=True,
                                        defaults={'description': 'Best-quality textured mesh workflow for client deliverables. Slower and memory intensive; use full-resolution source images.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'sfm-algorithm', 'value': 'triangulation'},
                                                              {'name': 'matcher-type', 'value': 'flann'},
                                                              {'name': 'matcher-neighbors', 'value': 8},
                                                              {'name': 'feature-quality', 'value': 'ultra'},
                                                              {'name': 'min-num-features', 'value': '30000'},
                                                              {'name': 'pc-quality', 'value': 'ultra'},
                                                              {'name': 'use-3dmesh', 'value': True},
                                                              {'name': 'mesh-octree-depth', 'value': '12'},
                                                              {'name': 'mesh-size', 'value': '2000000'},
                                                              {'name': 'gltf', 'value': True}]})
        Preset.objects.update_or_create(name='Gaussian Splat Source', system=True,
                                        defaults={'description': 'Highest-detail reconstruction source preset for Gaussian Splat post-processing. Produces ultra-quality point cloud, camera shots, and textured model assets for an external splat trainer.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'sfm-algorithm', 'value': 'triangulation'},
                                                              {'name': 'matcher-type', 'value': 'flann'},
                                                              {'name': 'matcher-neighbors', 'value': 8},
                                                              {'name': 'feature-quality', 'value': 'ultra'},
                                                              {'name': 'min-num-features', 'value': '30000'},
                                                              {'name': 'pc-quality', 'value': 'ultra'},
                                                              {'name': 'use-3dmesh', 'value': True},
                                                              {'name': 'mesh-octree-depth', 'value': '12'},
                                                              {'name': 'mesh-size', 'value': '2000000'},
                                                              {'name': 'gltf', 'value': True},
                                                              {'name': 'pc-las', 'value': True}]})
        Preset.objects.update_or_create(name='Volume Analysis', system=True,
                                        defaults={'description': 'DSM-focused output for stockpiles, piles, and other volume measurement workflows.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'dsm', 'value': True},
                                                              {'name': 'dem-resolution', 'value': '2'},
                                                              {'name': 'pc-quality', 'value': 'high'}]})
        Preset.objects.update_or_create(name='3D Model', system=True,
                                        defaults={'description': 'General 3D mesh processing with high point cloud quality and moderate mesh density.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'mesh-octree-depth', 'value': "12"},
                                                              {'name': 'use-3dmesh', 'value': True},
                                                              {'name': 'pc-quality', 'value': 'high'},
                                                              {'name': 'mesh-size', 'value': '300000'}]})
        Preset.objects.update_or_create(name='Buildings', system=True,
                                        defaults={'description': 'Aerial reconstruction preset tuned for buildings and structured surfaces.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'mesh-size', 'value': '300000'},
                                                              {'name': 'feature-quality', 'value': 'high'},
                                                              {'name': 'pc-quality', 'value': 'high'}]})
        Preset.objects.update_or_create(name='Forest', system=True,
                                        defaults={'description': 'Feature-focused processing for vegetation and forested areas.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'min-num-features', 'value': '18000'},
                                                              {'name': 'use-3dmesh', 'value': True},
                                                              {'name': 'feature-quality', 'value': 'medium'}]})
        Preset.objects.update_or_create(name='DSM + DTM', system=True,
                                        defaults={'description': 'Generate both surface and terrain elevation models.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'dsm', 'value': True},
                                                              {'name': 'dtm', 'value': True}]})
        Preset.objects.update_or_create(name='Field', system=True,
                                        defaults={'description': 'Fast planar mapping for field datasets where a quick orthophoto is more important than 3D detail.',
                                                  'options': [{'name': 'sfm-algorithm', 'value': 'planar'},
                                                              {'name': 'fast-orthophoto', 'value': True},
                                                              {'name': 'matcher-neighbors', 'value': 4}]})
        Preset.objects.update_or_create(name='Fast Orthophoto', system=True,
                                        defaults={'description': 'Quick orthophoto generation for preview or low-cost turnaround.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'fast-orthophoto', 'value': True}]})
        Preset.objects.update_or_create(name='High Resolution', system=True,
                                        defaults={'description': 'Higher-resolution orthophoto and DSM output for detailed 2D inspection.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'dsm', 'value': True},
                                                              {'name': 'pc-quality', 'value': 'high'},
                                                              {'name': 'dem-resolution', 'value': "2.0"},
                                                              {'name': 'orthophoto-resolution', 'value': "2.0"}]})
        Preset.objects.update_or_create(name='Default', system=True,
                                        defaults={'description': 'Safe default processing with automatic boundary and DSM generation.',
                                                  'options': [{'name': 'auto-boundary', 'value': True},
                                                              {'name': 'dsm', 'value': True}]})

    except MultipleObjectsReturned:
        # Mostly to handle a legacy code problem where
        # multiple system presets with the same name were
        # created if we changed the options
        Preset.objects.filter(system=True).delete()
        add_default_presets()
