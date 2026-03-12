from django.dispatch import receiver

from app.plugins import MountPoint, PluginBase, get_plugin_by_name, signals as plugin_signals


class Plugin(PluginBase):
    def include_js_files(self):
        return ['main.js']

    def build_jsx_components(self):
        return ['ThermalPanel.jsx']

    def api_mount_points(self):
        from .api.views import TaskThermalProcess, TaskThermalStatus

        return [
            MountPoint('task/(?P<pk>[^/.]+)/status$', TaskThermalStatus.as_view()),
            MountPoint('task/(?P<pk>[^/.]+)/process$', TaskThermalProcess.as_view()),
        ]


@receiver(plugin_signals.task_completed, dispatch_uid='thermal_ortho_on_task_completed')
def thermal_ortho_on_task_completed(sender, task_id, **kwargs):
    if get_plugin_by_name('thermal_ortho') is None:
        return

    from app.models import Task
    from .workers.thermal_pipeline import detect_input_summary, enqueue_thermal_pipeline, read_pipeline_status

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return

    summary = detect_input_summary(task.task_path())
    if summary['thermal_images'] == 0 or summary['rgb_images'] == 0:
        return

    status = read_pipeline_status(task)
    if status.get('state') in ('queued', 'running'):
        return

    enqueue_thermal_pipeline(task, camera_type='auto', trigger='auto', summary=summary)
