from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from app import models
from app.api.client_portal import get_active_share


def project_portal(request, token):
    share = get_active_share(token)
    project = share.project

    if request.method == 'POST':
        if share.role != models.ProjectClientShare.ROLE_REVIEWER:
            return HttpResponseForbidden(_("This client share is read-only."))

        author_name = request.POST.get('author_name', '').strip()
        author_email = request.POST.get('author_email', '').strip()
        body = request.POST.get('body', '').strip()

        if not author_name or not body:
            messages.error(request, _("Name and comment are required."))
        else:
            models.ProjectClientComment.objects.create(
                project=project,
                share=share,
                author_name=author_name,
                author_email=author_email,
                body=body,
            )
            messages.success(request, _("Comment added."))
            return redirect(share.portal_path())

    comments = models.ProjectClientComment.objects.filter(project=project, share=share).select_related(
        'task', 'issue'
    )
    issues = models.ProjectIssue.objects.filter(project=project).exclude(
        status=models.ProjectIssue.STATUS_CLOSED
    ).select_related('task').order_by('-updated_at', '-created_at')
    tasks = project.task_set.order_by('-created_at')

    return render(request, 'app/public/client_portal.html', {
        'title': project.name,
        'share': share,
        'project': project,
        'tasks': tasks,
        'issues': issues,
        'comments': comments,
        'api_url': '/api/client-shares/{}/'.format(share.token),
    })
