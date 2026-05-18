import json

from django.contrib.auth import login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from guardian.shortcuts import get_objects_for_user

from nodeodm.models import ProcessingNode
from app.models import Profile, Project, Task
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.utils.translation import gettext as _
from django import forms
from app.views.utils import get_permissions
from app.models import FeatureValidation
from app.services.feature_validation import log_feature_validation_change
from webodm import settings

def index(request):
    # Check first access
    if User.objects.filter(is_superuser=True).count() == 0:
        if settings.SINGLE_USER_MODE:
            # Automatically create a default account
            User.objects.create_superuser('admin', 'admin@localhost', 'admin')
        else:
            # the user is expected to create an admin account
            return redirect('welcome')

    if settings.SINGLE_USER_MODE and not request.user.is_authenticated:
        login(request, User.objects.get(username="admin"), 'django.contrib.auth.backends.ModelBackend')

    return redirect(settings.LOGIN_REDIRECT_URL if request.user.is_authenticated
                    else settings.LOGIN_URL)

@login_required
def dashboard(request):
    no_processingnodes = ProcessingNode.objects.count() == 0
    if no_processingnodes and settings.PROCESSING_NODES_ONBOARDING is not None:
        return redirect(settings.PROCESSING_NODES_ONBOARDING)

    no_tasks = Task.objects.filter(project__owner=request.user).count() == 0
    no_projects = Project.objects.filter(owner=request.user).count() == 0

    permissions = []
    if request.user.has_perm('app.add_project'):
        permissions.append('add_project')
    
    # Create first project automatically
    if settings.DASHBOARD_ONBOARDING and no_projects and 'add_project' in permissions:
        Project.objects.create(owner=request.user, name=_("First Project"))

    return render(request, 'app/dashboard.html', {'title': _('Dashboard'),
        'no_processingnodes': no_processingnodes,
        'no_tasks': no_tasks,
        'onboarding': settings.DASHBOARD_ONBOARDING,
        'params': {
            'permissions': json.dumps(permissions)
        }.items()
    })


@login_required
def map(request, project_pk=None, task_pk=None):
    title = _("Map")

    if project_pk is not None:
        project = get_object_or_404(Project, pk=project_pk)
        if not request.user.has_perm('app.view_project', project):
            raise Http404()
        
        if task_pk is not None:
            task = get_object_or_404(Task.objects.defer('orthophoto_extent', 'dsm_extent', 'dtm_extent'), pk=task_pk, project=project)
            title = task.name or task.id
            mapItems = [task.get_map_items()]
            projectInfo = None
        else:
            title = project.name or project.id
            mapItems = project.get_map_items()
            projectInfo = project.get_public_info()

    return render(request, 'app/map.html', {
            'title': title,
            'params': {
                'map-items': json.dumps(mapItems),
                'title': title,
                'public': 'false',
                'share-buttons': 'false' if settings.DESKTOP_MODE else 'true',
                'selected-map-type': request.GET.get('t', 'auto'),
                'permissions': json.dumps(get_permissions(request.user, project)),
                'project': json.dumps(projectInfo),
            }.items()
        })


@login_required
def model_display(request, project_pk=None, task_pk=None):
    title = _("3D Model Display")

    if project_pk is not None:
        project = get_object_or_404(Project, pk=project_pk)
        if not request.user.has_perm('app.view_project', project):
            raise Http404()

        if task_pk is not None:
            task = get_object_or_404(Task.objects.defer('orthophoto_extent', 'dsm_extent', 'dtm_extent'), pk=task_pk, project=project)
            title = task.name or task.id
        else:
            raise Http404()

    return render(request, 'app/3d_model_display.html', {
            'title': title,
            'params': {
                'task': json.dumps(task.get_model_display_params()),
                'public': 'false',
                'share-buttons': 'false' if settings.DESKTOP_MODE else 'true'
            }.items()
        })

def about(request):
    return render(request, 'app/about.html', {'title': _('About'), 'version': settings.VERSION})


@login_required
def account_token(request):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    return render(request, 'app/account_token.html', {
        'title': _('API Token'),
        'masked_api_key': profile.masked_api_key(),
    })


class FeatureValidationForm(forms.ModelForm):
    class Meta:
        model = FeatureValidation
        fields = (
            'key',
            'name',
            'area',
            'status',
            'test_notes',
            'maintenance_notes',
            'evidence_url',
        )


PIPELINE_AREAS = (
    ('P1', _('Mobile/Field Photo Capture')),
    ('P2', _('AI-Assisted Issue Detection')),
    ('P3', _('Client Sharing Portal')),
    ('P4', _('Textured Model QA + Sharing')),
    ('P5', _('Feature Validation Ledger')),
    ('P6', _('Core Platform Hardening')),
    ('P7', _('Monitoring Compare MVP')),
    ('P8', _('Project Timeline Monitoring')),
    ('P9', _('DSM/DTM Delta and Cut/Fill')),
    ('P10', _('Change Issues and Annotations')),
    ('P11', _('Advanced Alignment')),
    ('P12', _('Stakeholder Reports')),
    ('P13', _('Design/BIM/Plan Overlays')),
    ('P14', _('OneDrive Folder Task Intake')),
)


def _feature_validation_status_counts(features):
    return {
        status: sum(1 for feature in features if feature.status == status)
        for status, _label in FeatureValidation.STATUS_CHOICES
    }


def _feature_validation_area_summary(area, label, features):
    features = list(features)
    total = len(features)
    tested = sum(1 for feature in features if feature.status == FeatureValidation.STATUS_TESTED)
    attention = sum(1 for feature in features if feature.needs_attention)
    return {
        'area': area,
        'label': label,
        'features': features,
        'total': total,
        'tested': tested,
        'attention': attention,
        'coverage_percent': int(round((tested / total) * 100)) if total else 0,
        'status_counts': _feature_validation_status_counts(features),
    }


def _feature_validation_groups(all_features, include_empty_pipeline=True):
    features_by_area = {}
    for feature in all_features:
        features_by_area.setdefault(feature.area or _('Unassigned'), []).append(feature)

    groups = []
    used_areas = set()
    for area, label in PIPELINE_AREAS:
        used_areas.add(area)
        features = features_by_area.get(area, [])
        if include_empty_pipeline or features:
            groups.append(_feature_validation_area_summary(area, label, features))

    for area in sorted(area for area in features_by_area.keys() if area not in used_areas):
        groups.append(_feature_validation_area_summary(area, area, features_by_area.get(area, [])))

    return groups


@login_required
@user_passes_test(lambda user: user.is_staff)
def feature_validations(request):
    if request.method == 'POST':
        feature = None
        feature_id = request.POST.get('feature_id')
        if feature_id:
            feature = get_object_or_404(FeatureValidation, pk=feature_id)

        previous_status = feature.status if feature else None
        form = FeatureValidationForm(request.POST, instance=feature)
        if form.is_valid():
            feature = form.save(commit=False)
            if feature.status == FeatureValidation.STATUS_TESTED:
                feature.last_tested_by = request.user
                feature.last_tested_at = timezone.now()
            feature.save()
            log_feature_validation_change(feature, request.user, previous_status)
            messages.success(request, _("Feature validation saved."))
            return redirect('feature_validations')

        messages.error(request, _("Could not save feature validation. Please check the fields."))

    features = FeatureValidation.objects.select_related('last_tested_by').order_by(
        'area',
        'status',
        'name',
    )
    selected_status = request.GET.get('status', '')
    selected_area = request.GET.get('area', '')
    attention_only = request.GET.get('attention') in ('1', 'true', 'yes')

    if selected_status:
        features = features.filter(status=selected_status)
    if selected_area:
        features = features.filter(area=selected_area)
    if attention_only:
        features = features.filter(status__in=(
            FeatureValidation.STATUS_UNTESTED,
            FeatureValidation.STATUS_FAILING,
            FeatureValidation.STATUS_BLOCKED,
        ))

    all_features = list(FeatureValidation.objects.select_related('last_tested_by').order_by('area', 'name'))
    filtered_features = list(features)
    total_features = len(all_features)
    tested_count = sum(1 for feature in all_features if feature.status == FeatureValidation.STATUS_TESTED)
    attention_count = sum(1 for feature in all_features if feature.needs_attention)
    coverage_percent = int(round((tested_count / total_features) * 100)) if total_features else 0
    areas = sorted({feature.area for feature in all_features if feature.area})
    status_summaries = [
        {
            'status': status,
            'label': label,
            'count': sum(1 for feature in all_features if feature.status == status),
        }
        for status, label in FeatureValidation.STATUS_CHOICES
    ]
    groups = _feature_validation_groups(
        filtered_features,
        include_empty_pipeline=not (selected_status or selected_area or attention_only),
    )
    attention_features = [feature for feature in all_features if feature.needs_attention][:8]

    return render(request, 'app/feature_validations.html', {
        'title': _('Feature Validation'),
        'features': filtered_features,
        'feature_groups': groups,
        'attention_features': attention_features,
        'status_summaries': status_summaries,
        'total_features': total_features,
        'tested_count': tested_count,
        'attention_count': attention_count,
        'coverage_percent': coverage_percent,
        'areas': areas,
        'selected_status': selected_status,
        'selected_area': selected_area,
        'attention_only': attention_only,
        'status_choices': FeatureValidation.STATUS_CHOICES,
        'form': FeatureValidationForm(),
    })


def _format_processing_node_option_value(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return _('Yes') if value else _('No')
    return str(value)


def _processing_node_option_choices(option):
    domain = option.get('domain')
    if isinstance(domain, dict):
        return [
            {
                'value': _format_processing_node_option_value(value),
                'label': _format_processing_node_option_value(label or value),
            }
            for value, label in domain.items()
        ]
    if isinstance(domain, (list, tuple)):
        return [
            {
                'value': _format_processing_node_option_value(value),
                'label': _format_processing_node_option_value(value) or _('Default'),
            }
            for value in domain
        ]
    if option.get('type') == 'bool':
        return [
            {'value': _('Yes'), 'label': _('Yes')},
            {'value': _('No'), 'label': _('No')},
        ]
    return []


def _processing_node_options_view_model(available_options):
    if isinstance(available_options, str):
        try:
            available_options = json.loads(available_options)
        except ValueError:
            return []

    if isinstance(available_options, dict):
        available_options = available_options.get('options', [])

    option_rows = []
    for option in available_options or []:
        if not isinstance(option, dict):
            continue

        value = _format_processing_node_option_value(option.get('value'))
        choices = _processing_node_option_choices(option)
        selected_values = {choice['value'] for choice in choices}
        if choices and value and value not in selected_values:
            choices.insert(0, {'value': value, 'label': value})

        for choice in choices:
            choice['selected'] = choice['value'] == value

        option_rows.append({
            'name': option.get('name') or _('Unnamed option'),
            'type': option.get('type') or _('Option'),
            'help': option.get('help') or '',
            'value': value or _('Not set'),
            'choices': choices,
            'has_choices': len(choices) > 0,
        })

    return option_rows


@login_required
def processing_node(request, processing_node_id):
    pn = get_object_or_404(ProcessingNode, pk=processing_node_id)
    if not pn.update_node_info():
        messages.add_message(request, messages.constants.WARNING, _('%(node)s seems to be offline.') % {'node': pn})

    return render(request, 'app/processing_node.html', 
            {
                'title': _('Processing Node'), 
                'processing_node': pn,
                'processing_node_options': _processing_node_options_view_model(pn.available_options)
            })

class FirstUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('username', 'password', )
        widgets = {
            'password': forms.PasswordInput(),
        }


def welcome(request):
    if User.objects.filter(is_superuser=True).count() > 0:
        return redirect('index')

    fuf = FirstUserForm()

    if request.method == 'POST':
        fuf = FirstUserForm(request.POST)
        if fuf.is_valid():
            admin_user = fuf.save(commit=False)
            admin_user.password = make_password(fuf.cleaned_data['password'])
            admin_user.is_superuser = admin_user.is_staff = True
            admin_user.save()

            # Log-in automatically
            login(request, admin_user, 'django.contrib.auth.backends.ModelBackend')
            return redirect('dashboard')

    return render(request, 'app/welcome.html',
                  {
                      'title': _('Welcome'),
                      'firstuserform': fuf
                  })


def handler404(request, exception):
    return render(request, '404.html', status=404)

def handler500(request):
    return render(request, '500.html', status=500)


