from webodm import settings
from worker.celery import InMemoryAsyncResult, app


def get_async_result(celery_task_id):
    result_backend = InMemoryAsyncResult if settings.TESTING else app.AsyncResult
    return result_backend(celery_task_id)


def store_task_result(celery_task_id, result):
    if settings.TESTING:
        InMemoryAsyncResult.set(celery_task_id, result)
