import json
from datetime import datetime

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api import serializers

from apps.companies.models import Company
from apps.to_dos.filters import ToDoActionFilter, ToDoFilter
from apps.to_dos.models import ToDo, ToDoAction
from apps.to_dos.serializers import ToDoActionSerializer, ToDoSerializer
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager


class ToDoView(viewsets.ModelViewSet):
    serializer_class = ToDoSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ToDoFilter
    permissions = None

    ordering_fields = [
        "uuid",
        "created_at",
        "due_at",
        "company",
        "action",
        "responsibles",
    ]
    ordering = "created_at"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        self.permissions = PermissionManager(
            user=self.request.user,
            company_ids=Company.objects.all(),
            model="ToDo",
        )
        user_companies = self.permissions.companies_which_has_permission("can_view")

        queryset = ToDo.objects.filter(
            responsibles__in=[self.request.user], company_id__in=user_companies
        ).distinct()

        return self.get_serializer_class().setup_eager_loading(queryset)

    @action(methods=["PATCH"], url_path="BulkRead", detail=False)
    def bulk_read(self, request):
        data = json.loads(request.body)
        to_dos = data.get("to_dos", [])
        is_read = data.get("read", False)
        user = request.user
        qs_todo = ToDo.objects.filter(pk__in=to_dos, responsibles=user)

        if qs_todo.count() != len(to_dos):
            raise serializers.ValidationError(
                "kartado.error.to_do.user_is_not_responsible"
            )

        if is_read:
            for todo in qs_todo:
                todo.read_at = datetime.now()
                todo.save()

        else:
            for todo in qs_todo:
                todo.read_at = None
                todo.save()

        serializer = ToDoSerializer(qs_todo, many=True)
        return Response(serializer.data)


class ToDoActionView(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = ToDoActionSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ToDoActionFilter
    permissions = None

    ordering_fields = ["uuid", "created_by", "name"]
    ordering = "name"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        self.permissions = PermissionManager(
            user=self.request.user,
            company_ids=Company.objects.all(),
            model="ToDoAction",
        )

        queryset = ToDoAction.objects.filter(
            company_group=self.request.user.company_group
        ).distinct()

        return self.get_serializer_class().setup_eager_loading(queryset)
