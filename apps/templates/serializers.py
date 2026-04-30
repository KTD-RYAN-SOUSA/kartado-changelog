from django.db.models.signals import post_init, pre_init
from django.utils.timezone import now
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)

from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceType
from apps.templates.models import (
    ActionLog,
    AppVersion,
    CanvasCard,
    CanvasList,
    CSVImport,
    ExcelContractItemAdministration,
    ExcelContractItemUnitPrice,
    ExcelDnitReport,
    ExcelImport,
    ExcelReporting,
    ExportRequest,
    Log,
    MobileSync,
    PDFImport,
    PhotoReport,
    ReportingExport,
    SearchTag,
    SearchTagOccurrenceType,
    Template,
)
from apps.templates.notifications import send_email_export_request
from helpers.apps.excel_dnit_report import create_and_upload_excel_dnit_report
from helpers.apps.reporting_export import generate_reporting_export
from helpers.fields import EmptyFileField
from helpers.files import get_url
from helpers.mixins import EagerLoadingMixin, UUIDMixin
from helpers.signals import DisableSignals


class TemplateSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["companies"]

    uuid = serializers.UUIDField(required=False)
    companies = ResourceRelatedField(queryset=Company.objects, many=True)

    class Meta:
        model = Template
        fields = [
            "uuid",
            "companies",
            "model_name",
            "item_name",
            "options",
            "validation",
        ]

    def validate(self, data):
        """
        The companies, model_name and item_name fields must be unique_together,
        ie it is only possible to have a Template for a same model_name
        and item_name associated with a particular Company.
        """

        if "companies" in self.initial_data:
            for company in self.initial_data["companies"]:
                template = Template.objects.filter(
                    item_name=data["item_name"],
                    model_name=data["model_name"],
                    companies__pk=company["id"],
                )
                if template:
                    raise serializers.ValidationError(
                        "Já existe esse Template para essa Equipe"
                    )

        return data


class LogSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = Log
        fields = ["uuid", "company", "date", "description"]


class CanvasListSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["service_order", "created_by"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = CanvasList
        fields = [
            "uuid",
            "name",
            "kind",
            "order",
            "service_order",
            "created_at",
            "created_by",
            "color",
        ]
        read_only_fields = ["order"]


class CanvasCardSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["canvas_list", "created_by"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = CanvasCard
        fields = [
            "uuid",
            "name",
            "color",
            "description",
            "order",
            "extra_info",
            "canvas_list",
            "created_at",
            "created_by",
        ]
        read_only_fields = ["order"]


class AppVersionSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = AppVersion
        fields = [
            "uuid",
            "notification_title",
            "notification_body",
            "target_app",
            "target_platform",
            "start_date",
            "deadline",
            "version",
        ]


class ExportRequestSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["company", "created_by"]

    uuid = serializers.UUIDField(required=False)
    filename = serializers.CharField(required=False, source="file", write_only=True)

    class Meta:
        model = ExportRequest
        fields = [
            "uuid",
            "company",
            "created_by",
            "created_at",
            "done",
            "error",
            "filename",
            "file",
        ]

    def update(self, instance, validated_data):
        instance = super(ExportRequestSerializer, self).update(instance, validated_data)
        send_email_export_request(instance)
        return instance


class MobileSyncSerializer(serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin):
    _SELECT_RELATED_FIELDS = ["company", "created_by"]

    uuid = serializers.UUIDField(required=False)

    def update(self, instance, validated_data):
        # Autofill time_spent
        if validated_data["done"] and not instance.time_spent:
            validated_data["time_spent"] = (now() - instance.created_at).total_seconds()

        return super(MobileSyncSerializer, self).update(instance, validated_data)

    class Meta:
        model = MobileSync
        fields = [
            "uuid",
            "company",
            "created_by",
            "created_at",
            "kind",
            "done",
            "email_sent",
            "version",
            "connection",
            "latitude",
            "longitude",
            "speed",
            "has_error",
            "time_spent",
            "sync_post_data",
            "sync_get_data",
            "sync_steps_duration_data",
        ]


class ActionLogSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "company",
        "company_group",
        "user",
        "content_type",
        "content_object",
    ]

    uuid = serializers.UUIDField(required=False)
    content_object = ResourceRelatedField(read_only=True)
    object_exists = serializers.SerializerMethodField()

    class Meta:
        model = ActionLog
        fields = [
            "uuid",
            "company",
            "company_group",
            "user",
            "created_at",
            "action",
            "user_agent",
            "user_port",
            "user_ip",
            "content_object",
            "object_id",
            "content_type",
            "object_exists",
        ]

    def get_object_exists(self, obj):
        if obj.content_object:
            return True
        return False


class SearchTagSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company"]
    _PREFETCH_RELATED_FIELDS = ["parent_tags"]

    uuid = serializers.UUIDField(required=False)
    occurrence_type = SerializerMethodResourceRelatedField(
        model=OccurrenceType, method_name="get_occurrence_type", read_only=True
    )

    class Meta:
        model = SearchTag
        fields = [
            "uuid",
            "company",
            "name",
            "kind",
            "level",
            "occurrence_type",
            "parent_tags",
            "description",
            "redirect",
        ]

    def get_occurrence_type(self, obj):
        previous_tags = []
        if self.context and "previous_tags" in self.context:
            previous_tags = self.context["previous_tags"]
            previous_tags.append(obj.uuid)

        occurrence_type = SearchTagOccurrenceType.objects.filter(
            search_tags__in=previous_tags
        ).first()

        return occurrence_type.occurrence_type if occurrence_type else None


class ExcelImportSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "reportings",
        "company",
        "created_by",
        "contract_items_unit_price",
        "contract_items_administration",
    ]

    uuid = serializers.UUIDField(required=False)
    excel_file = EmptyFileField(required=False, allow_null=True)
    zip_file = EmptyFileField(required=False, allow_null=True)
    excel_file_url = serializers.SerializerMethodField()
    zip_file_url = serializers.SerializerMethodField()

    class Meta:
        model = ExcelImport
        fields = [
            "uuid",
            "company",
            "created_at",
            "created_by",
            "name",
            "zip_file",
            "zip_file_url",
            "excel_file",
            "excel_file_url",
            "preview_file",
            "done",
            "remaining_parts",
            "error",
            "generating_preview",
            "uploading_zip_images",
            "reportings",
            "is_over_limit",
            "is_forbidden",
            "contract_items_unit_price",
            "contract_items_administration",
        ]

        read_only_fields = ["generating_preview", "uploading_zip_images"]

    def get_excel_file_url(self, obj):
        return {}
        # kept this field here to maintain compatibility

    def get_zip_file_url(self, obj):
        return {}
        # kept this field here to maintain compatibility


class ExcelImportObjectSerializer(ExcelImportSerializer):
    def get_excel_file_url(self, obj):
        return get_url(obj, "excel_file")

    def get_zip_file_url(self, obj):
        return get_url(obj, "zip_file")


class ExcelReportingSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["reporting", "excel_import"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ExcelReporting
        fields = ["uuid", "reporting", "excel_import", "row", "operation"]
        # Add reporting, excel_import here to use serializer is_valid
        # method when passing ids
        extra_kwargs = {
            "reporting": {"required": False},
            "excel_import": {"required": False},
        }


class ExcelContractItemUnitPriceSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _PREFETCH_RELATED_FIELDS = ["contract_item_unit_price", "excel_import"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ExcelContractItemUnitPrice
        fields = [
            "uuid",
            "contract_item_unit_price",
            "excel_import",
            "row",
            "operation",
        ]
        extra_kwargs = {
            "contract_item_unit_price": {"required": False},
            "excel_import": {"required": False},
        }


class ExcelContractItemAdministrationSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _PREFETCH_RELATED_FIELDS = ["contract_item_administration", "excel_import"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ExcelContractItemAdministration
        fields = [
            "uuid",
            "contract_item_administration",
            "excel_import",
            "row",
            "operation",
        ]
        extra_kwargs = {
            "contract_item_administration": {"required": False},
            "excel_import": {"required": False},
        }


class PDFImportSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company", "created_by", "firm", "status"]
    _PREFETCH_RELATED_FIELDS = ["pdf_import_reportings"]

    uuid = serializers.UUIDField(required=False)
    pdf_file = EmptyFileField(required=False, allow_null=True)
    pdf_file_url = serializers.SerializerMethodField()

    class Meta:
        model = PDFImport
        fields = [
            "uuid",
            "company",
            "created_at",
            "created_by",
            "name",
            "pdf_file",
            "pdf_file_url",
            "preview_file",
            "done",
            "error",
            "firm",
            "menu",
            "status",
            "lane",
            "track",
            "branch",
            "km_reference",
            "description",
            "kind",
            "form_data",
            "occurrence_type",
            "pdf_import_reportings",
        ]
        read_only_fields = ["pdf_import_reportings"]

    def get_pdf_file_url(self, obj):
        """
        Kept to maintain compability. Meant to be overridden.
        """
        return {}


class PDFImportObjectSerializer(PDFImportSerializer):
    def get_pdf_file_url(self, obj):
        return get_url(obj, "pdf_file")


class CSVImportSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company", "created_by", "occurrence_type"]
    _PREFETCH_RELATED_FIELDS = ["csv_import_assays"]

    uuid = serializers.UUIDField(required=False)
    csv_file = EmptyFileField(required=False, allow_null=True)
    csv_file_url = serializers.SerializerMethodField()

    class Meta:
        model = CSVImport
        fields = [
            "uuid",
            "company",
            "created_at",
            "created_by",
            "name",
            "csv_file",
            "csv_file_url",
            "preview_file",
            "done",
            "error",
            "occurrence_type",
            "form_data",
            "csv_import_assays",
        ]
        read_only_fields = ["csv_import_assays"]
        extra_kwargs = {"occurrence_type": {"required": True}}

    def get_csv_file_url(self, obj):
        """
        Kept to maintain compability. Meant to be overridden.
        """
        return {}


class CSVImportObjectSerializer(CSVImportSerializer):
    def get_csv_file_url(self, obj):
        return get_url(obj, "csv_file")


class ReportingExportSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _PREFETCH_RELATED_FIELDS = ["company", "created_by"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ReportingExport
        fields = [
            "uuid",
            "company",
            "created_at",
            "created_by",
            "export_type",
            "extra_info",
            "is_inventory",
            "filters",
            "done",
            "error",
            "exported_file",
        ]

    def create(self, validated_data):
        with DisableSignals(
            disabled_signals=[
                pre_init,
                post_init,
            ]
        ):
            instance = super().create(validated_data)
            generate_reporting_export(str(instance.uuid))
            return instance


class ExcelDnitReportSerializer(
    serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin
):
    _PREFETCH_RELATED_FIELDS = ["company", "created_by"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = ExcelDnitReport
        fields = [
            "uuid",
            "company",
            "created_at",
            "created_by",
            "extra_info",
            "filters",
            "done",
            "error",
            "exported_file",
        ]

    def create(self, validated_data):
        with DisableSignals(
            disabled_signals=[
                pre_init,
                post_init,
            ]
        ):
            instance = super().create(validated_data)
            create_and_upload_excel_dnit_report(str(instance.uuid))
            return instance


class PhotoReportSerializer(serializers.ModelSerializer, EagerLoadingMixin, UUIDMixin):
    _PREFETCH_RELATED_FIELDS = ["company", "created_by"]

    uuid = serializers.UUIDField(required=False)
    options_file = EmptyFileField(required=False, allow_null=True)
    options_file_url = serializers.SerializerMethodField()
    exported_file = EmptyFileField(required=False, allow_null=True)
    exported_file_url = serializers.SerializerMethodField()

    class Meta:
        model = PhotoReport
        fields = [
            "uuid",
            "export_type",
            "is_inventory",
            "company",
            "options",
            "options_file",
            "options_file_url",
            "created_by",
            "created_at",
            "done",
            "error",
            "processing_finished_at",
            "exported_file",
            "exported_file_url",
        ]

    def get_options_file_url(self, obj):
        return get_url(obj, "options_file")

    def get_exported_file_url(self, obj):
        return get_url(obj, "exported_file")
