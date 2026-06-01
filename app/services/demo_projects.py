import os

import numpy as np
import rasterio
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.base import ContentFile
from django.utils import timezone
from rasterio.enums import ColorInterp
from rasterio.transform import from_bounds

from app import models
from app.services.commercial_readiness import build_project_commercial_readiness
from nodeodm import status_codes


DEMO_PROJECTS = (
    {
        "key": "architecture",
        "name": "Demo - Architecture CAD Orthomosaic",
        "description": "Sample construction progress project for CAD/design overlay comparison and client reporting.",
        "package": models.ProjectCommercialReadiness.PACKAGE_ARCHITECTURE_CAD,
        "task_name": "Construction Demo Flight",
        "bounds": (57.490, -20.165, 57.496, -20.159),
        "assets": ("orthophoto.tif", "dsm.tif", "dtm.tif"),
        "overlay": True,
        "issue": {
            "title": "Resolved slab edge review",
            "issue_type": models.ProjectIssue.ISSUE_TYPE_PROGRESS,
            "priority": models.ProjectIssue.PRIORITY_MEDIUM,
            "status": models.ProjectIssue.STATUS_RESOLVED,
        },
    },
    {
        "key": "agriculture",
        "name": "Demo - Agriculture Field Analysis",
        "description": "Sample field analysis project for plant-health review and scouting follow-up.",
        "package": models.ProjectCommercialReadiness.PACKAGE_AGRICULTURE_FIELD,
        "task_name": "Field Analysis Demo Flight",
        "bounds": (57.540, -20.220, 57.552, -20.208),
        "assets": ("orthophoto.tif", "dsm.tif"),
        "field_photo": True,
        "multispectral": True,
        "issue": {
            "title": "Resolved irrigation scouting zone",
            "issue_type": models.ProjectIssue.ISSUE_TYPE_ANNOTATION,
            "priority": models.ProjectIssue.PRIORITY_MEDIUM,
            "status": models.ProjectIssue.STATUS_RESOLVED,
        },
    },
    {
        "key": "solar",
        "name": "Demo - Solar Panel Inspection",
        "description": "Sample solar inspection project for panel issue mapping and thermal follow-up.",
        "package": models.ProjectCommercialReadiness.PACKAGE_SOLAR_INSPECTION,
        "task_name": "Solar Inspection Demo Flight",
        "bounds": (57.600, -20.245, 57.608, -20.237),
        "assets": ("orthophoto.tif", "dsm.tif", "thermal_orthophoto.tif"),
        "field_photo": True,
        "issue": {
            "title": "Resolved row hotspot review",
            "issue_type": models.ProjectIssue.ISSUE_TYPE_DEFECT,
            "priority": models.ProjectIssue.PRIORITY_HIGH,
            "status": models.ProjectIssue.STATUS_RESOLVED,
        },
    },
)


def _extent_geometry(bounds):
    west, south, east, north = bounds
    return GEOSGeometry(
        "POLYGON (({west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}))".format(
            west=west,
            south=south,
            east=east,
            north=north,
        ),
        srid=4326,
    )


def _write_raster(path, bounds, kind="orthophoto", multispectral=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    width = 96
    height = 96
    transform = from_bounds(*bounds, width=width, height=height)
    grid_y, grid_x = np.indices((height, width))

    if kind == "dem":
        values = (50 + grid_x * 0.08 + grid_y * 0.03).astype("float32")
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=-9999,
        ) as dst:
            dst.write(values, 1)
        return

    if kind == "thermal":
        values = (28 + ((grid_x // 12) % 2) * 8 + ((grid_y // 18) % 2) * 3).astype("float32")
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=-9999,
        ) as dst:
            dst.write(values, 1)
            dst.set_band_description(1, "thermal")
        return

    red = (80 + grid_x * 1.2).clip(0, 255).astype("uint8")
    green = (70 + grid_y * 1.5).clip(0, 255).astype("uint8")
    blue = (180 - ((grid_x + grid_y) * 0.8)).clip(0, 255).astype("uint8")
    bands = [red, green, blue]
    descriptions = ["red", "green", "blue"]
    colorinterp = [ColorInterp.red, ColorInterp.green, ColorInterp.blue]

    if multispectral:
        nir = (120 + (grid_x * 0.7) + (grid_y * 0.5)).clip(0, 255).astype("uint8")
        bands.append(nir)
        descriptions.append("nir")
        colorinterp.append(ColorInterp.undefined)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=len(bands),
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
        nodata=0,
    ) as dst:
        for index, values in enumerate(bands, start=1):
            dst.write(values, index)
            dst.set_band_description(index, descriptions[index - 1])
        dst.colorinterp = tuple(colorinterp)


def _write_demo_assets(task, definition):
    bounds = definition["bounds"]
    if "orthophoto.tif" in definition["assets"]:
        _write_raster(
            task.assets_path("odm_orthophoto", "odm_orthophoto.tif"),
            bounds,
            multispectral=definition.get("multispectral", False),
        )
        task.orthophoto_extent = _extent_geometry(bounds)
    if "dsm.tif" in definition["assets"]:
        _write_raster(task.assets_path("odm_dem", "dsm.tif"), bounds, kind="dem")
        task.dsm_extent = _extent_geometry(bounds)
    if "dtm.tif" in definition["assets"]:
        _write_raster(task.assets_path("odm_dem", "dtm.tif"), bounds, kind="dem")
        task.dtm_extent = _extent_geometry(bounds)
    if "thermal_orthophoto.tif" in definition["assets"]:
        _write_raster(task.assets_path("thermal_orthophoto", "thermal_orthophoto.tif"), bounds, kind="thermal")

    task.status = status_codes.COMPLETED
    task.update_available_assets_field()
    task.update_epsg_field()
    task.update_orthophoto_bands_field()
    task.save()


def _ensure_task(project, definition):
    task = project.task_set.filter(name=definition["task_name"]).first()
    if task is None:
        task = models.Task.objects.create(
            project=project,
            name=definition["task_name"],
            status=status_codes.COMPLETED,
            created_at=timezone.now(),
        )
    _write_demo_assets(task, definition)
    return task


def _ensure_design_overlay(project, owner, definition):
    if not definition.get("overlay"):
        return None
    overlay = project.design_overlays.filter(name="Demo Site Plan").first()
    if overlay is None:
        overlay = models.ProjectDesignOverlay(project=project, name="Demo Site Plan", created_by=owner)
    west, south, east, north = definition["bounds"]
    geojson = (
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"Planned Footprint"},'
        '"geometry":{"type":"Polygon","coordinates":[[[%s,%s],[%s,%s],[%s,%s],[%s,%s],[%s,%s]]]}}]}'
        % (west, south, east, south, east, north, west, north, west, south)
    )
    overlay.file.save("demo-site-plan.geojson", ContentFile(geojson.encode("utf-8")), save=False)
    overlay.source_filename = "demo-site-plan.geojson"
    overlay.save()
    return overlay


def _ensure_field_photo(project, owner, task, definition):
    if not definition.get("field_photo"):
        return None
    photo = project.field_photos.filter(name="Demo Field Photo").first()
    if photo is None:
        west, south, east, north = definition["bounds"]
        photo = models.ProjectFieldPhoto(
            project=project,
            task=task,
            name="Demo Field Photo",
            description="Synthetic field evidence for demo review.",
            location={"type": "Point", "coordinates": [(west + east) / 2, (south + north) / 2]},
            created_by=owner,
        )
    # Minimal valid PNG.
    photo.image.save(
        "demo-field-photo.png",
        ContentFile(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
            b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
        ),
        save=False,
    )
    photo.source_filename = "demo-field-photo.png"
    photo.save()
    return photo


def _ensure_issue(project, owner, task, definition):
    issue_definition = definition["issue"]
    issue = project.issues.filter(title=issue_definition["title"]).first()
    if issue is None:
        issue = models.ProjectIssue(project=project, title=issue_definition["title"], created_by=owner)
    issue.task = task
    issue.issue_type = issue_definition["issue_type"]
    issue.priority = issue_definition["priority"]
    issue.status = issue_definition["status"]
    issue.description = "Synthetic resolved review item for commercial demo workflows."
    issue.save()
    return issue


def _ensure_client_share(project, owner):
    share = project.client_shares.filter(name="Demo Client Review").first()
    if share is None:
        share = models.ProjectClientShare(project=project, name="Demo Client Review", created_by=owner)
    share.role = models.ProjectClientShare.ROLE_REVIEWER
    share.enabled = True
    share.expires_at = timezone.now() + timezone.timedelta(days=30)
    share.save()
    return share


def _ensure_commercial_readiness(project, owner, definition):
    readiness, _created = models.ProjectCommercialReadiness.objects.get_or_create(project=project)
    readiness.package = definition["package"]
    readiness.deliverables_reviewed = True
    readiness.human_reviewed = True
    readiness.report_reviewed = True
    readiness.client_share_reviewed = True
    readiness.legal_disclaimer_reviewed = True
    readiness.notes = "Synthetic demo project generated for sales, onboarding, and training."
    readiness.updated_by = owner
    readiness.save()
    return readiness


def create_demo_projects(owner):
    results = []
    for definition in DEMO_PROJECTS:
        project, created = models.Project.objects.get_or_create(
            owner=owner,
            name=definition["name"],
            defaults={"description": definition["description"]},
        )
        if project.description != definition["description"]:
            project.description = definition["description"]
            project.save(update_fields=["description"])

        task = _ensure_task(project, definition)
        _ensure_design_overlay(project, owner, definition)
        _ensure_field_photo(project, owner, task, definition)
        _ensure_issue(project, owner, task, definition)
        _ensure_client_share(project, owner)
        _ensure_commercial_readiness(project, owner, definition)
        readiness = build_project_commercial_readiness(project)

        results.append(
            {
                "key": definition["key"],
                "project": project,
                "created": created,
                "task": task,
                "ready": readiness["ready"],
                "package": definition["package"],
                "report_url": "/api/projects/{}/reports/progress?format=html".format(project.id),
                "readiness_url": "/api/projects/{}/commercial/readiness".format(project.id),
            }
        )

    return results
