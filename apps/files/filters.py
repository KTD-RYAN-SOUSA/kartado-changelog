from django.contrib.contenttypes.models import ContentType
from django_filters import rest_framework as filters
from django_filters.filters import ChoiceFilter

from apps.constructions.models import Construction, ConstructionProgress
from apps.files.models import File
from apps.monitorings.models import MonitoringRecord, OperationalControl
from apps.occurrence_records.models import OccurrenceRecord
from apps.service_orders.const import file_choices
from helpers.filters import ListFilter, UUIDListFilter
from helpers.strings import check_image_file


class FileFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    file_type = ChoiceFilter(
        choices=file_choices.FILE_CHOICES,
        method="check_image",
        label="file_type",
    )
    construction = ListFilter(method="get_construction")
    construction_progress = ListFilter(method="get_construction_progress")
    monitoring_record = ListFilter(method="get_monitoring_record")
    operational_control = ListFilter(method="get_operational_control")
    occurrence_record = ListFilter(method="get_occurrence_record")

    class Meta:
        model = File
        fields = ["company"]

    def check_image(self, queryset, name, value):
        ids_and_file_names = queryset.values_list("uuid", "upload")
        if value == "image":
            list_get = [
                item[0] for item in ids_and_file_names if check_image_file(item[1])
            ]
        elif value == "file":
            list_get = [
                item[0] for item in ids_and_file_names if not check_image_file(item[1])
            ]

        return queryset.filter(pk__in=list_get)

    def get_monitoring_record(self, queryset, name, value):
        ids = value.split(",")

        return queryset.filter(
            monitoring_record_file__in=ids,
            content_type=ContentType.objects.get_for_model(MonitoringRecord),
        )

    def get_operational_control(self, queryset, name, value):
        ids = value.split(",")

        return queryset.filter(
            op_control_file__in=ids,
            content_type=ContentType.objects.get_for_model(OperationalControl),
        )

    def get_construction(self, queryset, name, value):
        ids = value.split(",")

        return queryset.filter(
            file_constructions__in=ids,
            content_type=ContentType.objects.get_for_model(Construction),
        )

    def get_construction_progress(self, queryset, name, value):
        ids = value.split(",")

        return queryset.filter(
            file_construction_progresses__in=ids,
            content_type=ContentType.objects.get_for_model(ConstructionProgress),
        )

    def get_occurrence_record(self, queryset, name, value):
        ids = value.split(",")

        return queryset.filter(
            record_file__in=ids,
            content_type=ContentType.objects.get_for_model(OccurrenceRecord),
        )
