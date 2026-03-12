from rest_framework import status
from rest_framework.response import Response

from app.api.common import get_and_check_project
from app.plugins.views import TaskView
from nodeodm import status_codes

from coreplugins.thermal_ortho.workers.thermal_pipeline import (
    build_status_payload,
    detect_input_summary,
    enqueue_thermal_pipeline,
    read_pipeline_status,
)


class TaskThermalStatus(TaskView):
    def get(self, request, pk=None):
        task = self.get_and_check_task(request, pk)
        return Response(build_status_payload(task), status=status.HTTP_200_OK)


class TaskThermalProcess(TaskView):
    def post(self, request, pk=None):
        task = self.get_and_check_task(request, pk)

        if task.check_public_edit():
            get_and_check_project(request, task.project.id, ('change_project',))

        if task.status != status_codes.COMPLETED and 'thermal_orthophoto.tif' not in (task.available_assets or []):
            return Response({'error': 'Task must finish ODM processing before thermal generation can start.'}, status=status.HTTP_200_OK)

        camera_type = request.data.get('camera_type', 'auto')
        if camera_type not in ('auto', 'dji', 'flir'):
            return Response({'error': 'camera_type must be one of auto, dji, flir.'}, status=status.HTTP_200_OK)

        current = read_pipeline_status(task)
        if current.get('state') in ('queued', 'running') and current.get('celery_task_id'):
            return Response(build_status_payload(task), status=status.HTTP_200_OK)

        summary = detect_input_summary(task.task_path())
        if summary['thermal_images'] == 0:
            return Response({'error': 'No thermal images were detected for this task.'}, status=status.HTTP_200_OK)
        if summary['rgb_images'] == 0:
            return Response({'error': 'Thermal images were found, but no RGB images are available for geometry.'}, status=status.HTTP_200_OK)

        celery_result = enqueue_thermal_pipeline(task, camera_type=camera_type, trigger='manual', summary=summary)
        payload = build_status_payload(task)
        payload['celery_task_id'] = celery_result.task_id
        return Response(payload, status=status.HTTP_200_OK)
