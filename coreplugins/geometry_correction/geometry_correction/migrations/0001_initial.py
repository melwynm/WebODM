from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CorrectionJob",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True)),
                ("task_id", models.CharField(db_index=True, max_length=128)),
                ("project_id", models.IntegerField()),
                ("celery_task_id", models.CharField(blank=True, max_length=255, null=True)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("running", "Running"),
                        ("completed", "Completed"),
                        ("failed", "Failed"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("options", models.JSONField(default=dict)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "Correction Job"},
        ),
    ]
