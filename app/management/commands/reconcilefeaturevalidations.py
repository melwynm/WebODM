from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from app.models import FeatureValidation
from app.services.feature_validation import reconcile_pipeline_feature_validations


class Command(BaseCommand):
    help = "Create or update canonical pipeline and commercial feature validation ledger records."

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            choices=[choice[0] for choice in FeatureValidation.STATUS_CHOICES],
            default=None,
            help='Optional status to apply to every canonical validation record.',
        )
        parser.add_argument(
            '--tested',
            action='store_true',
            help='Shortcut for --status tested.',
        )
        parser.add_argument(
            '--overwrite-notes',
            action='store_true',
            help='Overwrite existing test and maintenance notes with canonical notes.',
        )
        parser.add_argument(
            '--user',
            default='',
            help='Username to record as last tester when marking records tested.',
        )

    def handle(self, *args, **options):
        if options['tested'] and options['status']:
            raise CommandError("--tested cannot be combined with --status.")

        status = FeatureValidation.STATUS_TESTED if options['tested'] else options['status']
        user = None
        if options['user']:
            try:
                user = get_user_model().objects.get(username=options['user'])
            except get_user_model().DoesNotExist:
                raise CommandError("User does not exist: {}".format(options['user']))

        results = reconcile_pipeline_feature_validations(
            status=status,
            overwrite=options['overwrite_notes'],
            user=user,
        )
        created = sum(1 for _feature, was_created, _changed in results if was_created)
        changed = sum(1 for _feature, was_created, was_changed in results if was_changed and not was_created)
        tested = sum(1 for feature, _created, _changed in results if feature.status == FeatureValidation.STATUS_TESTED)

        self.stdout.write(
            self.style.SUCCESS(
                "Reconciled {} feature validations (created {}, updated {}, tested {}).".format(
                    len(results),
                    created,
                    changed,
                    tested,
                )
            )
        )
