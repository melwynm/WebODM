import os
import tempfile
import zipfile
import shutil

from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect, HttpResponseNotAllowed, JsonResponse
from django.urls import re_path, reverse
from django.utils.html import format_html
from guardian.admin import GuardedModelAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from app.models import PluginDatum
from app.models import Preset
from app.models import Plugin
from app.models import Profile
from app.plugins import get_plugin_by_name, enable_plugin, disable_plugin, delete_plugin, valid_plugin, \
    get_plugins_persistent_path, clear_plugins_cache, init_plugins
from .models import Project, Task, Setting, Theme, ProjectIssue, ProjectDesignOverlay, ProjectFieldPhoto, \
    ProjectClientShare, ProjectClientComment, FeatureValidation
from django import forms
from codemirror2.widgets import CodeMirrorEditor
from webodm import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.translation import gettext_lazy as _, gettext


class ProjectAdmin(GuardedModelAdmin):
    list_display = ('id', 'name', 'owner', 'created_at', 'tasks_count', 'tags')
    list_filter = ('owner',)
    search_fields = ('id', 'name', 'owner__username')


admin.site.register(Project, ProjectAdmin)


class TaskAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    list_display = ('id', 'name', 'project', 'processing_node', 'created_at', 'status', 'last_error')
    list_filter = ('status', 'project',)
    search_fields = ('id', 'name', 'project__name')


admin.site.register(Task, TaskAdmin)

admin.site.register(Preset, admin.ModelAdmin)


class ProjectIssueAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'project', 'task', 'issue_type', 'status', 'priority', 'created_by', 'assigned_to', 'updated_at')
    list_filter = ('issue_type', 'status', 'priority', 'created_at', 'updated_at')
    search_fields = ('title', 'description', 'project__name', 'task__name', 'created_by__username', 'assigned_to__username')
    readonly_fields = ('created_at', 'updated_at', 'closed_at')


admin.site.register(ProjectIssue, ProjectIssueAdmin)


class ProjectDesignOverlayAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'source_filename', 'created_by', 'updated_at')
    search_fields = ('name', 'description', 'source_filename', 'project__name')
    list_filter = ('created_at', 'updated_at')


admin.site.register(ProjectDesignOverlay, ProjectDesignOverlayAdmin)


class ProjectFieldPhotoAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'task', 'is_360', 'source_filename', 'created_by', 'updated_at')
    search_fields = ('name', 'description', 'source_filename', 'project__name', 'task__name', 'created_by__username')
    list_filter = ('is_360', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


admin.site.register(ProjectFieldPhoto, ProjectFieldPhotoAdmin)


class ProjectClientShareAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'role', 'enabled', 'expires_at', 'created_by', 'updated_at')
    list_filter = ('role', 'enabled', 'created_at', 'updated_at')
    search_fields = ('name', 'project__name', 'created_by__username', 'token')
    readonly_fields = ('token', 'created_at', 'updated_at')


admin.site.register(ProjectClientShare, ProjectClientShareAdmin)


class ProjectClientCommentAdmin(admin.ModelAdmin):
    list_display = ('author_name', 'project', 'share', 'task', 'issue', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('author_name', 'author_email', 'body', 'project__name', 'share__name')
    readonly_fields = ('created_at',)


admin.site.register(ProjectClientComment, ProjectClientCommentAdmin)


class FeatureValidationAdmin(admin.ModelAdmin):
    list_display = ('key', 'name', 'area', 'status', 'last_tested_by', 'last_tested_at', 'updated_at')
    list_filter = ('status', 'area', 'last_tested_at', 'updated_at')
    search_fields = ('key', 'name', 'area', 'test_notes', 'maintenance_notes')
    readonly_fields = ('last_tested_at', 'created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        if obj.status == FeatureValidation.STATUS_TESTED and obj.last_tested_by_id is None:
            obj.last_tested_by = request.user
        super().save_model(request, obj, form, change)


admin.site.register(FeatureValidation, FeatureValidationAdmin)


class SettingAdminForm(forms.ModelForm):
    class Meta:
        model = Setting
        fields = '__all__'
        widgets = {
            'openai_api_key': forms.PasswordInput(render_value=True),
        }


class SettingAdmin(admin.ModelAdmin):
    form = SettingAdminForm
    fieldsets = (
        (None, {
            'fields': ('app_name', 'app_logo', 'organization_name', 'organization_website', 'theme')
        }),
        (_("AI-assisted issue detection"), {
            'fields': ('openai_api_key', 'openai_model')
        }),
    )

    def has_add_permission(self, request):
        # if there's already an entry, do not allow adding
        count = Setting.objects.all().count()
        return count == 0


admin.site.register(Setting, SettingAdmin)


class ThemeColorInput(forms.TextInput):
    input_type = 'color'

    def __init__(self, attrs=None):
        default_attrs = {'class': 'theme-color-picker'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def format_value(self, value):
        value = super().format_value(value) or '#000000'
        if value and not value.startswith('#'):
            value = '#{}'.format(value)
        return value


class ThemeModelForm(forms.ModelForm):
    COLOR_FIELDS = (
        'primary',
        'secondary',
        'tertiary',
        'button_primary',
        'button_default',
        'button_danger',
        'header_background',
        'header_primary',
        'border',
        'highlight',
        'dialog_warning',
        'failed',
        'success',
    )

    css = forms.CharField(help_text=_("Enter custom CSS"),
                          label=_("CSS"),
                          required=False,
                          widget=CodeMirrorEditor(options={'mode': 'css', 'lineNumbers': True}))
    html_before_header = forms.CharField(help_text=_("HTML that will be displayed above site header"),
                                         label=_("HTML (before header)"),
                                         required=False,
                                         widget=CodeMirrorEditor(options={'mode': 'xml', 'lineNumbers': True}))
    html_after_header = forms.CharField(help_text=_("HTML that will be displayed after site header"),
                                        label=_("HTML (after header)"),
                                        required=False,
                                        widget=CodeMirrorEditor(options={'mode': 'xml', 'lineNumbers': True}))
    html_after_body = forms.CharField(help_text=_("HTML that will be displayed after the body tag"),
                                      label=_("HTML (after body)"),
                                      required=False,
                                      widget=CodeMirrorEditor(options={'mode': 'xml', 'lineNumbers': True}))
    html_footer = forms.CharField(help_text=_(
        "HTML that will be displayed in the footer. You can also use the special tags such as {ORGANIZATION} and {YEAR}."),
        label=_("HTML (footer)"),
        required=False,
        widget=CodeMirrorEditor(options={'mode': 'xml', 'lineNumbers': True}))

    class Meta:
        model = Theme
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.COLOR_FIELDS:
            self.fields[field_name].widget = ThemeColorInput()


class ThemeAdmin(admin.ModelAdmin):
    fields = ('name',)
    readonly_fields = ('name',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Theme, ThemeAdmin)
admin.site.register(PluginDatum, admin.ModelAdmin)


class PluginAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "version", "author", "enabled", "plugin_actions")
    readonly_fields = ("name",)
    change_list_template = "admin/change_list_plugin.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def description(self, obj):
        manifest = get_plugin_by_name(obj.name, only_active=False, refresh_cache_if_none=True).get_manifest()
        return _(manifest.get('description', ''))

    description.short_description = _("Description")

    def version(self, obj):
        manifest = get_plugin_by_name(obj.name, only_active=False, refresh_cache_if_none=True).get_manifest()
        return manifest.get('version', '')

    version.short_description = _("Version")

    def author(self, obj):
        manifest = get_plugin_by_name(obj.name, only_active=False, refresh_cache_if_none=True).get_manifest()
        return manifest.get('author', '')

    author.short_description = _("Author")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            re_path(
                r'^(?P<plugin_name>.+)/enable/$',
                self.admin_site.admin_view(self.plugin_enable),
                name='plugin-enable',
            ),
            re_path(
                r'^(?P<plugin_name>.+)/disable/$',
                self.admin_site.admin_view(self.plugin_disable),
                name='plugin-disable',
            ),
            re_path(
                r'^(?P<plugin_name>.+)/delete/$',
                self.admin_site.admin_view(self.plugin_delete),
                name='plugin-delete',
            ),
            re_path(
                r'^actions/upload/$',
                self.admin_site.admin_view(self.plugin_upload),
                name='plugin-upload',
            ),
        ]
        return custom_urls + urls

    def plugin_enable(self, request, plugin_name, *args, **kwargs):
        try:
            p = enable_plugin(plugin_name)
            if p.requires_restart():
                messages.warning(request, _("Restart required. Please restart WebODM to enable %(plugin)s") % {
                    'plugin': plugin_name})
        except Exception as e:
            messages.warning(request, _("Cannot enable plugin %(plugin)s: %(message)s") % {'plugin': plugin_name,
                                                                                           'message': str(e)})

        return HttpResponseRedirect(reverse('admin:app_plugin_changelist'))

    def plugin_disable(self, request, plugin_name, *args, **kwargs):
        try:
            p = disable_plugin(plugin_name)
            if p.requires_restart():
                messages.warning(request, _("Restart required. Please restart WebODM to fully disable %(plugin)s") % {
                    'plugin': plugin_name})
        except Exception as e:
            messages.warning(request, _("Cannot disable plugin %(plugin)s: %(message)s") % {'plugin': plugin_name,
                                                                                            'message': str(e)})

        return HttpResponseRedirect(reverse('admin:app_plugin_changelist'))

    def plugin_delete(self, request, plugin_name, *args, **kwargs):
        try:
            delete_plugin(plugin_name)
        except Exception as e:
            messages.warning(request, _("Cannot delete plugin %(plugin)s: %(message)s") % {'plugin': plugin_name,
                                                                                           'message': str(e)})

        return HttpResponseRedirect(reverse('admin:app_plugin_changelist'))

    def plugin_upload(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        if file is not None:
            # Save to tmp dir
            tmp_zip_path = tempfile.mktemp('plugin.zip', dir=settings.MEDIA_TMP)
            tmp_extract_path = tempfile.mkdtemp('plugin', dir=settings.MEDIA_TMP)

            try:
                with open(tmp_zip_path, 'wb+') as fd:
                    if isinstance(file, InMemoryUploadedFile):
                        for chunk in file.chunks():
                            fd.write(chunk)
                    else:
                        with open(file.temporary_file_path(), 'rb') as f:
                            shutil.copyfileobj(f, fd)

                # Extract
                with zipfile.ZipFile(tmp_zip_path, "r") as zip_h:
                    zip_h.extractall(tmp_extract_path)

                # Validate
                folders = os.listdir(tmp_extract_path)
                if len(folders) != 1:
                    raise ValueError("The plugin has more than 1 root directory (it should have only one)")

                plugin_name = folders[0]
                plugin_path = os.path.join(tmp_extract_path, plugin_name)
                if not valid_plugin(plugin_path):
                    raise ValueError(
                        "This doesn't look like a plugin. Are plugin.py and manifest.json in the proper place?")

                if os.path.exists(get_plugins_persistent_path(plugin_name)):
                    raise ValueError(
                        "A plugin with the name {} already exist. Please remove it before uploading one with the same name.".format(
                            plugin_name))

                # Move
                shutil.move(plugin_path, get_plugins_persistent_path())

                # Initialize
                clear_plugins_cache()
                init_plugins()

                messages.info(request, _("Plugin added successfully"))
            except Exception as e:
                messages.warning(request, _("Cannot load plugin: %(message)s") % {'message': str(e)})
                if os.path.exists(tmp_zip_path):
                    os.remove(tmp_zip_path)
                if os.path.exists(tmp_extract_path):
                    shutil.rmtree(tmp_extract_path)
        else:
            messages.error(request, _("You need to upload a zip file"))

        return HttpResponseRedirect(reverse('admin:app_plugin_changelist'))

    def plugin_actions(self, obj):
        plugin = get_plugin_by_name(obj.name, only_active=False)
        return format_html(
            '<a class="button" href="{}" {}>{}</a>&nbsp;'
            '<a class="button" href="{}" {}>{}</a>'
            + (
                '&nbsp;<a class="button" href="{}" onclick="return confirm(\'Are you sure you want to delete {}?\')"><i class="fa fa-trash"></i></a>' if not plugin.is_persistent() else '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;')
            ,
            reverse('admin:plugin-disable', args=[obj.pk]) if obj.enabled else '#',
            'disabled' if not obj.enabled else '',
            _('Disable'),
            reverse('admin:plugin-enable', args=[obj.pk]) if not obj.enabled else '#',
            'disabled' if obj.enabled else '',
            _('Enable'),
            reverse('admin:plugin-delete', args=[obj.pk]),
            obj.name
        )

    plugin_actions.short_description = _('Actions')
    plugin_actions.allow_tags = True


admin.site.register(Plugin, PluginAdmin)

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    fields = ('quota', 'api_token_management')
    readonly_fields = ('api_token_management',)

    class Media:
        css = {'all': ('app/css/api-token-management.css',)}
        js = ('app/js/api-token-management.js',)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ['api_token_management']
        return list(self.fields)

    def api_token_management(self, obj):
        if obj is None or not getattr(obj, 'user_id', None):
            return _("Save the user account first to generate an API token.")

        return mark_safe(render_to_string('app/includes/api_token_manager.html', {
            'masked_api_key': obj.masked_api_key(),
            'fetch_url': reverse('admin:auth_user_api_token', args=[obj.user_id]),
            'regenerate_url': reverse('admin:auth_user_api_token_regenerate', args=[obj.user_id]),
        }))

    api_token_management.short_description = _("API Token")


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            re_path(
                r'^(?P<user_id>[^/.]+)/api-token/$',
                self.admin_site.admin_view(self.api_token_view),
                name='auth_user_api_token',
            ),
            re_path(
                r'^(?P<user_id>[^/.]+)/api-token/regenerate/$',
                self.admin_site.admin_view(self.regenerate_api_token_view),
                name='auth_user_api_token_regenerate',
            ),
        ]
        return custom_urls + urls

    def get_token_user(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        if not self.has_change_permission(request, user):
            raise PermissionDenied
        return user

    def api_token_view(self, request, user_id, *args, **kwargs):
        user = self.get_token_user(request, user_id)
        profile, _created = Profile.objects.get_or_create(user=user)
        return JsonResponse({'api_key': profile.api_key})

    def regenerate_api_token_view(self, request, user_id, *args, **kwargs):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])

        user = self.get_token_user(request, user_id)
        profile, _created = Profile.objects.get_or_create(user=user)
        profile.regenerate_api_key()
        return JsonResponse({'api_key': profile.api_key})


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)



