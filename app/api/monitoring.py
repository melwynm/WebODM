from rest_framework import exceptions, serializers, status
from rest_framework.response import Response
from django.http import HttpResponse

from rio_tiler.io import COGReader
from rio_tiler.profiles import img_profiles
from rio_tiler.utils import has_alpha_band, non_alpha_indexes

from app.api.tasks import TaskNestedView
from app.monitoring import MonitoringError, ensure_monitoring_products, monitoring_layer_path
from nodeodm import status_codes
from worker import tasks as worker_tasks


class MonitoringCompareSerializer(serializers.Serializer):
    compare_task = serializers.CharField(help_text="Task ID to compare against the current task")


class MonitoringCandidates(TaskNestedView):
    def get(self, request, pk=None, project_pk=None):
        task = self.get_and_check_task(request, pk)
        candidates = task.project.task_set.filter(status=status_codes.COMPLETED).exclude(pk=task.id).order_by("-created_at")
        data = [
            {
                "id": str(candidate.id),
                "name": candidate.name,
                "created_at": candidate.created_at.isoformat(),
            }
            for candidate in candidates
            if "orthophoto.tif" in (candidate.available_assets or [])
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

        try:
            compare_task = task.project.task_set.get(pk=compare_task_id)
        except Exception:
            raise exceptions.ValidationError("The comparison task could not be found in this project")

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
