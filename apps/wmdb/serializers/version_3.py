from rest_framework import serializers

from apps.reportings.models import Reporting
from apps.reportings.serializers import ReportingSerializer


class InventorySerializer(ReportingSerializer):
    id = serializers.ReadOnlyField(source="uuid")
    uuid_id = serializers.ReadOnlyField(source="uuid")

    class Meta:
        model = Reporting
        fields = [
            "id",
            "uuid_id",
            "branch",
            "direction",
            "editable",
            "lane",
            "lot",
            "number",
            "occurrence_kind",
            "road_name",
            "track",
            "end_km",
            "km",
            "km_reference",
            "project_end_km",
            "project_km",
            "end_km_manually_specified",
            "project_end_km_manually_specified",
            "form_data",
            "form_metadata",
            "point",
            "created_at",
            "executed_at",
            "found_at",
            "updated_at",
            "company_id",
            "created_by_id",
            "firm_id",
            "job_id",
            "occurrence_type_id",
            "road_id",
            "status_id",
            "active_inspection_id",
            "feature_collection",
            "active_tile_layer_id",
            "active_shape_files",
        ]
        read_only_fields = fields
        extra_kwargs = {"services": {"required": False}}
