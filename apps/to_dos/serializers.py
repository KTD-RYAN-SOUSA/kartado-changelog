from rest_framework_json_api import serializers
from rest_framework_json_api.relations import ResourceRelatedField

from apps.to_dos.models import ToDo, ToDoAction
from apps.users.models import User
from helpers.mixins import EagerLoadingMixin


class ToDoSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "resource",
        "destination_resource",
        "responsibles",
        "action",
        "company",
        "created_by",
        "resource_type",
        "destination_resource_type",
    ]

    resource = ResourceRelatedField(read_only=True)
    destination_resource = ResourceRelatedField(read_only=True)
    responsibles = ResourceRelatedField(queryset=User.objects, many=True)
    see = serializers.SerializerMethodField()

    class Meta:
        model = ToDo
        fields = [
            "uuid",
            "company",
            "created_at",
            "due_at",
            "read_at",
            "created_by",
            "responsibles",
            "action",
            "description",
            "is_done",
            "url",
            "destination",
            "resource_type",
            "resource_obj_id",
            "resource",
            "destination_resource_type",
            "destination_resource_obj_id",
            "destination_resource",
            "see",
        ]
        read_only_fields = ["created_at", "see"]

    def get_see(self, obj):
        return (
            True
            if getattr(obj, "action") and obj.action.default_options == "see"
            else False
        )


class ToDoActionSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company_group", "created_by"]

    class Meta:
        model = ToDoAction
        fields = ["uuid", "company_group", "created_by", "name"]
