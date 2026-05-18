from django.utils import timezone
from rest_framework import permissions, serializers, viewsets

from app import models
from app.services.feature_validation import log_feature_validation_change


class FeatureValidationSerializer(serializers.ModelSerializer):
    last_tested_by_username = serializers.ReadOnlyField(source='last_tested_by.username')
    needs_attention = serializers.ReadOnlyField()
    attention_reason = serializers.ReadOnlyField()

    class Meta:
        model = models.FeatureValidation
        fields = (
            'id',
            'key',
            'name',
            'area',
            'status',
            'test_notes',
            'maintenance_notes',
            'evidence_url',
            'last_tested_by',
            'last_tested_by_username',
            'last_tested_at',
            'needs_attention',
            'attention_reason',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'last_tested_by',
            'last_tested_by_username',
            'last_tested_at',
            'needs_attention',
            'attention_reason',
            'created_at',
            'updated_at',
        )


class FeatureValidationViewSet(viewsets.ModelViewSet):
    serializer_class = FeatureValidationSerializer
    permission_classes = (permissions.IsAdminUser,)
    filter_backends = ()
    lookup_field = 'key'
    lookup_value_regex = '[^/]+'

    def paginate_queryset(self, queryset):
        if self.paginator and self.request.query_params.get(self.paginator.page_query_param, None) is None:
            return None
        return super().paginate_queryset(queryset)

    def get_queryset(self):
        queryset = models.FeatureValidation.objects.select_related('last_tested_by')
        status_value = self.request.query_params.get('status')
        if status_value:
            queryset = queryset.filter(status=status_value)

        area = self.request.query_params.get('area')
        if area:
            queryset = queryset.filter(area=area)

        if self.request.query_params.get('attention') in ('1', 'true', 'yes'):
            queryset = queryset.filter(status__in=(
                models.FeatureValidation.STATUS_UNTESTED,
                models.FeatureValidation.STATUS_FAILING,
                models.FeatureValidation.STATUS_BLOCKED,
            ))

        return queryset

    def perform_create(self, serializer):
        status_value = serializer.validated_data.get('status', models.FeatureValidation.STATUS_UNTESTED)
        kwargs = {}
        if status_value == models.FeatureValidation.STATUS_TESTED:
            kwargs = {
                'last_tested_by': self.request.user,
                'last_tested_at': timezone.now(),
            }
        feature = serializer.save(**kwargs)
        log_feature_validation_change(feature, self.request.user)

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        status_value = serializer.validated_data.get('status', previous_status)
        kwargs = {}
        if status_value == models.FeatureValidation.STATUS_TESTED and previous_status != status_value:
            kwargs = {
                'last_tested_by': self.request.user,
                'last_tested_at': timezone.now(),
            }
        feature = serializer.save(**kwargs)
        log_feature_validation_change(feature, self.request.user, previous_status)
