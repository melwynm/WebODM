from django.http import HttpResponse
from rest_framework import exceptions, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from rio_tiler.io import COGReader
from rio_tiler.profiles import img_profiles
from rio_tiler.utils import has_alpha_band, non_alpha_indexes

from app.api.common import get_and_check_project
from app.api.tasks import TaskNestedView
from app.monitoring import MonitoringError, ensure_monitoring_products, monitoring_layer_path
from nodeodm import status_codes
from worker import tasks as worker_tasks


class MonitoringCompareSerializer(serializers.Serializer):
    compare_task = serializers.CharField(help_text="Task ID to compare against the current task")


def completed_orthophoto_tasks(project, exclude_task_id=None):
    exclude_task_id = str(exclude_task_id) if exclude_task_id is not None else None
    tasks = project.task_set.filter(status=status_codes.COMPLETED).order_by("created_at", "id")
    return [
        task
        for task in tasks
        if str(task.id) != exclude_task_id and "orthophoto.tif" in (task.available_assets or [])
    ]


def default_monitoring_compare_task_id(tasks, reference_task_id):
    if not tasks or reference_task_id is None:
        return None

    reference_index = next((idx for idx, task in enumerate(tasks) if str(task.id) == str(reference_task_id)), None)
    if reference_index is None:
        return None
    if len(tasks) < 2:
        return None
    if reference_index > 0:
        return str(tasks[reference_index - 1].id)
    if reference_index + 1 < len(tasks):
        return str(tasks[reference_index + 1].id)
    return None


class MonitoringTimeline(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, project_pk=None):
        project = get_and_check_project(request, project_pk)
        context_task_id = request.query_params.get("task")
        timeline_tasks = completed_orthophoto_tasks(project)

        default_reference_task_id = None
        if timeline_tasks:
            if context_task_id and any(str(task.id) == str(context_task_id) for task in timeline_tasks):
                default_reference_task_id = str(context_task_id)
            else:
                default_reference_task_id = str(timeline_tasks[-1].id)

        results = []
        for index, timeline_task in enumerate(timeline_tasks):
            results.append(
                {
                    "id": str(timeline_task.id),
                    "name": timeline_task.name,
                    "created_at": timeline_task.created_at.isoformat(),
                    "position": index + 1,
                    "previous_task_id": str(timeline_tasks[index - 1].id) if index > 0 else None,
                    "next_task_id": str(timeline_tasks[index + 1].id) if index + 1 < len(timeline_tasks) else None,
                    "is_context": str(timeline_task.id) == str(context_task_id),
                }
            )

        return Response(
            {
                "results": results,
                "default_reference_task_id": default_reference_task_id,
                "default_compare_task_id": default_monitoring_compare_task_id(
                    timeline_tasks, default_reference_task_id
                ),
                "timeline_order": "created_at",
            }
        )


class MonitoringCandidates(TaskNestedView):
    def get(self, request, pk=None, project_pk=None):
        task = self.get_and_check_task(request, pk)
        candidates = list(reversed(completed_orthophoto_tasks(task.project, exclude_task_id=task.id)))
        data = [
            {
                "id": str(candidate.id),
                "name": candidate.name,
                "created_at": candidate.created_at.isoformat(),
            }
            for candidate in candidates
        ]
        return Response({"results": data})


class MonitoringCompare(TaskNestedView):
    def post(self, request, pk=None, project_pk=None):
        task = self.get_and_check_task(request, pk)
        serializer = MonitoringCompareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        compare_task_id = serializer.validated_data["compare_task"]
        if str(task.id) == compare_task_id:
            raise exceptions.ValidationError("Please select a different task to compare")

        if "orthophoto.tif" not in (task.available_assets or []):
            raise exceptions.ValidationError("The reference task does not have an orthophoto")

        try:
            compare_task = task.project.task_set.get(pk=compare_task_id)
        except Exception:
            raise exceptions.ValidationError("The comparison task could not be found in this project")

        if compare_task.status != status_codes.COMPLETED:
            raise exceptions.ValidationError("The comparison task is not completed yet")

        if "orthophoto.tif" not in (compare_task.available_assets or []):
            raise exceptions.ValidationError("The comparison task does not have an orthophoto")

        celery_task_id = worker_tasks.generate_monitoring_compare.delay(str(task.id), str(compare_task.id)).task_id
        return Response({"celery_task_id": celery_task_id}, status=status.HTTP_200_OK)


class MonitoringTiles(TaskNestedView):
    def get(self, request, pk=None, project_pk=None, compare_task_pk=None, layer_type=None, z=None, x=None, y=None, scale=1, ext=None):
        task = self.get_and_check_task(request, pk)

        try:
            compare_task = task.project.task_set.get(pk=compare_task_pk)
        except Exception:
            raise exceptions.NotFound()

        try:
            ensure_monitoring_products(task, compare_task)
            path = monitoring_layer_path(task, compare_task, layer_type)
        except MonitoringError as e:
            raise exceptions.ValidationError(str(e))

        return render_monitoring_tile(path, request, z, x, y, scale, ext)


def render_monitoring_tile(path, request, z, x, y, scale=1, ext=None):
    z = int(z)
    x = int(x)
    y = int(y)
    scale = int(scale)

    tilesize = request.query_params.get("size")
    rescale = request.query_params.get("rescale")

    if tilesize in (None, ""):
        tilesize = 256
    try:
        tilesize = int(tilesize)
    except ValueError:
        raise exceptions.ValidationError("Invalid tile size parameter")

    if tilesize not in (256, 512):
        raise exceptions.ValidationError("Invalid tile size parameter")

    if tilesize == 512:
        z -= 1
    tilesize = tilesize * scale

    with COGReader(path) as src:
        if not src.tile_exists(x, y, z):
            raise exceptions.NotFound("Outside of bounds")

        indexes = None
        colorinterp = src.dataset.colorinterp
        if len(colorinterp) > 4:
            if has_alpha_band(src.dataset):
                indexes = non_alpha_indexes(src.dataset)
            else:
                indexes = (1, 2, 3)
        elif has_alpha_band(src.dataset):
            indexes = non_alpha_indexes(src.dataset)

        tile_kwargs = {
            "tilesize": tilesize,
            "nodata": 0,
        }
        if indexes is not None:
            tile_kwargs["indexes"] = indexes

        try:
            tile = src.tile(x, y, z, **tile_kwargs)
        except TypeError:
            tile_kwargs.pop("indexes", None)
            tile = src.tile(x, y, z, **tile_kwargs)

        if ext is None:
            if (tile.mask == 255).all():
                ext = "jpg"
            else:
                ext = "png"

        driver = "jpeg" if ext == "jpg" else ext
        options = img_profiles.get(driver, {})

        if rescale not in (None, ""):
            try:
                rescale_arr = list(map(float, rescale.replace("%2C", ",").split(",")))
            except ValueError:
                raise exceptions.ValidationError("Invalid rescale value")
            data = tile.post_process(in_range=(rescale_arr,))
            rendered = data.render(img_format=driver, **options)
        else:
            rendered = tile.render(img_format=driver, **options)

        return HttpResponse(rendered, content_type=f"image/{ext}")