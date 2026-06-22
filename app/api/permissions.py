from app.api.common import get_and_check_project


class ProjectPermissionPolicy:
    """Single API-facing entry point for project object permission checks."""

    VIEW = ("view_project",)
    CHANGE = ("change_project",)
    DELETE = ("delete_project",)
    AIRTWIN_ACKNOWLEDGE = ("acknowledge_airtwin_import",)

    @staticmethod
    def get_project(request, project_pk, perms=VIEW):
        return get_and_check_project(request, project_pk, perms)
