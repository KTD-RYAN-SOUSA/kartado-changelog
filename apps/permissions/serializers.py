from django.db.models import Prefetch
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import ResourceRelatedField

from apps.companies.models import Company
from helpers.mixins import EagerLoadingMixin

from .models import PermissionOccurrenceKindRestriction, UserPermission


class UserPermissionSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("companies", queryset=Company.objects.all().only("uuid")),
        Prefetch(
            "occurrence_kind_restrictions",
            queryset=PermissionOccurrenceKindRestriction.objects.all().only(
                "uuid", "user_permission_id", "company_id", "allowed_occurrence_kinds"
            ),
        ),
    ]

    uuid = serializers.UUIDField(required=False)
    companies = ResourceRelatedField(queryset=Company.objects, many=True)
    occurrence_kind_restrictions = serializers.SerializerMethodField()

    class Meta:
        model = UserPermission
        fields = [
            "uuid",
            "companies",
            "name",
            "permissions",
            "is_admin",
            "occurrence_kind_restrictions",
        ]

    def get_occurrence_kind_restrictions(self, obj):
        """
        Returns a dict mapping company_uuid to list of allowed occurrence kinds.
        Example: {"company-uuid-1": ["1", "2"], "company-uuid-2": ["3", "4"]}
        Empty dict means no restrictions (full access to all kinds).
        """
        # Use prefetched data if available, otherwise query
        restrictions = obj.occurrence_kind_restrictions.all()

        result = {}
        for restriction in restrictions:
            company_uuid = str(restriction.company_id)
            if restriction.allowed_occurrence_kinds:
                result[company_uuid] = restriction.allowed_occurrence_kinds
        return result

    def update(self, instance, validated_data):
        try:
            transitions = {}
            for status in validated_data["permissions"]["procedure"][
                "allowed_status_transitions"
            ].keys():
                status_fixed = status.replace("_", "-")
                transitions[status_fixed] = validated_data["permissions"]["procedure"][
                    "allowed_status_transitions"
                ][status]
            validated_data["permissions"]["procedure"][
                "allowed_status_transitions"
            ] = transitions
        except Exception as e:
            print("Exception trying to reset permissions!", repr(e))

        return super(UserPermissionSerializer, self).update(instance, validated_data)

    def create(self, validated_data):
        try:
            transitions = {}
            for status in validated_data["permissions"]["procedure"][
                "allowed_status_transitions"
            ].keys():
                status_fixed = status.replace("_", "-")
                transitions[status_fixed] = validated_data["permissions"]["procedure"][
                    "allowed_status_transitions"
                ][status]
            validated_data["permissions"]["procedure"][
                "allowed_status_transitions"
            ] = transitions
        except Exception as e:
            print("Exception trying to reset permissions!", repr(e))

        return super(UserPermissionSerializer, self).create(validated_data)
