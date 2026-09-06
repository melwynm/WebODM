import json

from django import forms
from django.contrib import messages
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.translation import gettext as _

from app import models
from app.api.client_portal import get_active_share


class ProjectClientCommentForm(forms.ModelForm):
    class Meta:
        model = models.ProjectClientComment
        fields = ('author_name', 'author_email', 'body')


def project_portal(request, token):
    share = get_active_share(token)
    project = share.project
    comment_form = ProjectClientCommentForm(request.POST or None)

    if request.method == 'POST':
        if share.role != models.ProjectClientShare.ROLE_REVIEWER:
            return HttpResponseForbidden(_("This client share is read-only."))

        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.project = project
            comment.share = share
            comment.save()
            messages.success(request, _("Comment added."))
            return redirect(share.portal_path())
        messages.error(request, _("Please correct the comment fields below."))

    comments = models.ProjectClientComment.objects.filter(project=project, share=share).select_related(
        'task', 'issue'
    )
    issues = models.ProjectIssue.objects.filter(project=project).exclude(
        status=models.ProjectIssue.STATUS_CLOSED
    ).select_related('task').order_by('-updated_at', '-created_at')
    tasks = project.task_set.order_by('-created_at')
    monitoring_runs = models.ProjectMonitoringRun.objects.filter(
        project=project,
        client_share=share,
        status=models.ProjectMonitoringRun.STATUS_PUBLISHED,
    ).select_related('current_task', 'baseline_task')

    return render(request, 'app/public/client_portal.html', {
        'title': project.name,
        'share': share,
        'project': project,
        'tasks': tasks,
        'issues': issues,
        'comments': comments,
        'monitoring_runs': monitoring_runs,
        'comment_form': comment_form,
        'api_url': '/api/client-shares/{}/'.format(share.token),
    })


@ensure_csrf_cookie
def model_display(request, token, task_pk):
    share = get_active_share(token)
    try:
        task = models.Task.objects.get(pk=task_pk, project=share.project)
    except models.Task.DoesNotExist:
        raise Http404

    return render(request, 'app/public/3d_model_display.html', {
        'title': task.name,
        'params': {
            'task': json.dumps(task.get_model_display_params()),
            'public': 'true',
            'public-edit': 'false',
            'share-buttons': 'false',
            'model-type': request.GET.get('t', 'mesh'),
            'client-token': str(share.token),
        }.items()
    })
