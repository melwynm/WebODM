from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

import app.models.project_issue


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0049_add_dji_drone_preset'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectIssue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('issue_type', models.CharField(choices=[('annotation', 'Annotation'), ('change', 'Change'), ('defect', 'Defect'), ('progress', 'Progress')], default='annotation', max_length=24)),
                ('status', models.CharField(choices=[('open', 'Open'), ('in_review', 'In Review'), ('resolved', 'Resolved'), ('closed', 'Closed')], db_index=True, default='open', max_length=24)),
                ('priority', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], db_index=True, default='medium', max_length=24)),
                ('geometry', models.JSONField(blank=True, null=True, validators=[app.models.project_issue.validate_geojson_geometry])),
                ('properties', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_project_issues', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_project_issues', to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='issues', to='app.project')),
                ('task', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='issues', to='app.task')),
            ],
            options={
                'verbose_name': 'Project Issue',
                'verbose_name_plural': 'Project Issues',
                'ordering': ('-updated_at', '-created_at'),
            },
        ),
    ]
