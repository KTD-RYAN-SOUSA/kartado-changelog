from uuid import UUID

from django.contrib.gis.geos import Polygon
from django.db.models import Q, TextField, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Concat
from django_filters import rest_framework as filters
from django_filters.filters import CharFilter
from django_filters.rest_framework.filters import BooleanFilter
from rest_framework_json_api import serializers

from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceRecord
from apps.templates.models import SearchTag
from helpers.apps.occurrence_records import apply_conditions_to_query
from helpers.apps.record_panel import handle_field_name
from helpers.filters import (
    DateFromToRangeCustomFilter,
    JSONFieldOrderingFilter,
    KeyFilter,
    ListFilter,
    UUIDListFilter,
)
from helpers.strings import get_obj_from_path, is_valid_uuid

from .models import (
    CustomDashboard,
    CustomTable,
    DataSeries,
    OccurrenceRecordWatcher,
    OccurrenceType,
    OccurrenceTypeSpecs,
    RecordPanel,
    TableDataSeries,
)


class OccurrenceTypeFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    active = BooleanFilter(method="get_active")
    is_last_version = BooleanFilter(
        field_name="next_version", lookup_expr="isnull", label="is_last_version"
    )
    occurrence_kind = ListFilter()
    occurrence_kind__exclude = ListFilter(field_name="occurrence_kind", exclude=True)
    service_order = UUIDListFilter(field_name="type_records__service_orders")
    is_not_listed = BooleanFilter(method="get_is_not_listed")
    name = CharFilter(lookup_expr="unaccent__icontains")
    search = CharFilter(label="search", method="get_search")
    company = filters.UUIDFilter()
    created_by = UUIDListFilter()

    class Meta:
        model = OccurrenceType
        fields = {
            "company": ["exact"],
            "firms": ["exact"],
            "show_in_web_map": ["exact"],
            "show_in_app_map": ["exact"],
            "color": ["exact"],
            "icon": ["exact"],
            "icon_size": ["exact"],
        }

    def get_active(self, queryset, name, value):
        company_id = self.data.get("company", "")
        for_list_filter = self.data.get("for_list_filter", False)
        if for_list_filter and company_id:
            try:
                company = Company.objects.get(pk=company_id)
                show_inactive = get_obj_from_path(
                    company.metadata, "show_inactive_occurrence_types_in_filter"
                )
                if show_inactive:
                    return queryset
            except Exception:
                pass
        return queryset.filter(active=value)

    def get_is_not_listed(self, queryset, name, value):
        company_id = self.data.get("company", "")
        if not company_id:
            return queryset

        if value:
            return queryset.filter(
                occurrencetype_specs__is_not_listed=True,
                occurrencetype_specs__company=company_id,
            ).distinct()
        else:
            return queryset.exclude(
                occurrencetype_specs__is_not_listed=True,
                occurrencetype_specs__company=company_id,
            ).distinct()

    def get_search(self, queryset, name, value):
        return queryset.filter(name__unaccent__icontains=value).distinct()


class ParameterGroupFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    monitoring_plan = UUIDListFilter()

    class Meta:
        model = OccurrenceType
        fields = {"company": ["exact"], "occurrence_kind": ["exact"]}


class OccurrenceTypeSpecsFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    is_not_listed = BooleanFilter()

    class Meta:
        model = OccurrenceTypeSpecs
        fields = {"company": ["exact"], "occurrence_type": ["exact"]}


class OccurrenceRecordFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    geom = CharFilter(method="get_geom", label="geom")
    uf_code = ListFilter()
    city = UUIDListFilter()
    location = UUIDListFilter()
    place_on_dam = ListFilter()
    river = UUIDListFilter()
    origin = ListFilter()
    origin_media = ListFilter()
    created_by = UUIDListFilter()
    occurrence_type = ListFilter(method="get_occurrence_type")
    firm = UUIDListFilter()
    operational_control = UUIDListFilter()
    monitoring_plan = UUIDListFilter()
    entity = UUIDListFilter(field_name="firm__entity")
    status = UUIDListFilter()
    parent_action = UUIDListFilter()
    action = UUIDListFilter(field_name="service_orders__actions")
    service_order = UUIDListFilter(field_name="service_orders")
    occurrence_kind = CharFilter(field_name="occurrence_type__occurrence_kind")
    datetime = DateFromToRangeCustomFilter()
    created_at = DateFromToRangeCustomFilter()
    updated_at = DateFromToRangeCustomFilter()
    is_closed = BooleanFilter(
        label="service_order__is_closed", method="is_closed_filter"
    )
    has_parent_action = BooleanFilter(
        field_name="parent_action",
        exclude=True,
        lookup_expr="isnull",
        label="has_parent_action",
    )
    has_service_order = BooleanFilter(
        field_name="service_orders",
        exclude=True,
        lookup_expr="isnull",
        label="has_service_order",
    )
    is_done = CharFilter(label="is_done", method="is_done_filter")
    search = CharFilter(label="search", method="get_search")
    involved_parts = CharFilter(
        label="involved_parts", method="get_involved_parts_keywords"
    )
    created_by_firm = ListFilter(method="get_created_by_firm")
    form_data__accident_type = ListFilter()
    form_data = KeyFilter(allow_null=True)
    is_not_listed = BooleanFilter(method="get_is_not_listed")
    is_config_occurrence_type = BooleanFilter(method="get_is_config_occurrence_type")
    record_panel = CharFilter(method="apply_record_panel_conditions")
    main_linked_record = UUIDListFilter()
    other_linked_records = UUIDListFilter()

    # SearchTags
    search_tags = UUIDListFilter()
    register_tag = ListFilter(method="get_register_tag")
    type_tag = ListFilter(method="get_type_tag")
    kind_tag = UUIDListFilter(field_name="search_tags")
    subject_tag = ListFilter(method="get_subject_tag")

    datetime__hour = ListFilter(field_name="datetime__hour")

    # Validation
    validation_deadline = DateFromToRangeCustomFilter()
    validated_at = DateFromToRangeCustomFilter()
    number = CharFilter(label="N° Registro", method="get_number_register")

    class Meta:
        model = OccurrenceRecord
        fields = {
            "company": ["exact"],
            "distance_from_dam": ["range"],
        }

    def get_is_not_listed(self, queryset, name, value):
        company_id = self.data.get("company", "")
        if not company_id:
            return queryset

        if value:
            return queryset.filter(
                occurrence_type__occurrencetype_specs__is_not_listed=True,
                occurrence_type__occurrencetype_specs__company=company_id,
            ).distinct()
        else:
            return queryset.exclude(
                occurrence_type__occurrencetype_specs__is_not_listed=True,
                occurrence_type__occurrencetype_specs__company=company_id,
            ).distinct()

    def get_is_config_occurrence_type(self, queryset, name, value):
        company_id = self.data.get("company", "")
        if not company_id:
            return queryset

        conditions = {
            "occurrence_type__occurrence_type_op_controls__firm__company": company_id
        }

        if value:
            return queryset.filter(**conditions)
        else:
            return queryset.exclude(**conditions)

    def get_register_tag(self, queryset, name, value):
        try:
            values = value.split(",")
            company = Company.objects.get(pk=self.request.query_params["company"])
            possible_path = (
                "occurrencerecord__fields__occurrencekind__selectoptions__options"
            )
            options = get_obj_from_path(company.custom_options, possible_path)
            options_translated = {item["name"]: item["value"] for item in options}
            names = (
                SearchTag.objects.filter(pk__in=values)
                .values_list("name", flat=True)
                .distinct()
            )
            kinds = [options_translated.get(item) for item in names]
        except Exception:
            return queryset
        else:
            return queryset.filter(
                Q(search_tags__in=values)
                | Q(occurrence_type__occurrence_kind__in=kinds)
            )

    def get_type_tag(self, queryset, name, value):
        values = value.split(",")
        return queryset.filter(
            Q(search_tags__in=values) | Q(occurrence_type__in=values)
        )

    def get_subject_tag(self, queryset, name, value):
        values = value.split(",")
        search_tags_uuids = [item for item in values if is_valid_uuid(item)]
        return queryset.filter(
            Q(search_tags__in=search_tags_uuids)
            | Q(operational_control__kind__in=values)
        )

    def get_occurrence_type(self, queryset, name, value):
        ids = value.split(",")
        occ_types = OccurrenceType.objects.filter(
            type_records__in=queryset
        ).values_list("uuid", "previous_version_id")
        list_ids = []

        def get_previous_id(obj_id, occ_types):
            for obj, pre_obj in occ_types:
                if str(obj) == obj_id and pre_obj:
                    return str(pre_obj)
            return None

        for obj_id in ids:
            while obj_id:
                list_ids.append(obj_id)
                obj_id = get_previous_id(obj_id, occ_types)

        return queryset.filter(occurrence_type_id__in=list_ids).distinct()

    def get_created_by_firm(self, queryset, name, value):
        ids = value.split(",")

        return queryset.filter(created_by__user_firms__in=ids).distinct()

    def is_closed_filter(self, queryset, name, value):
        if value:
            return queryset.filter(service_orders__is_closed=True)
        else:
            return queryset.filter(
                Q(service_orders__is_closed=False) | Q(service_orders__isnull=True)
            )

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "keywords",
                Value(" "),
                "involved_parts_keywords",
                Value(" "),
                "other_reference",
                Value(" "),
                "number",
                Value(" "),
                "occurrence_type__name",
                Value(" "),
                "location__name",
                Value(" "),
                "river__name",
                Value(" "),
                "city__name",
                Value(" "),
                "search_tags__name",
                Value(" "),
                "search_tag_description",
                Value(" "),
                KeyTextTransform("action", "form_data"),
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def get_involved_parts_keywords(self, queryset, name, value):
        return queryset.filter(
            involved_parts_keywords__unaccent__icontains=value
        ).distinct()

    def is_done_filter(self, queryset, name, value):
        company_metadata = Company.objects.get(
            uuid=self.request.query_params["company"]
        ).metadata
        if "special_filters" in company_metadata:
            special_filters = company_metadata["special_filters"]

            if value not in special_filters.keys():
                return queryset

            has_service_order = special_filters[value].get("has_service_order", None)
            status_ids = special_filters[value].get("status_ids", None)

            fields = ["has_service_order", "status_ids"]
            keys = special_filters[value].keys()

            if set(fields).issubset(keys):
                return queryset.filter(status_id__in=status_ids).exclude(
                    service_orders__isnull=has_service_order
                )
            elif "has_service_order" in keys:
                return queryset.exclude(service_orders__isnull=has_service_order)
            elif "status_ids" in keys:
                return queryset.filter(status_id__in=status_ids)

        return queryset

    def get_geom(self, queryset, name, value):
        if value:
            try:
                # xmin, ymin, xmax, ymax (like Point which is x,y)
                bbox = [float(item) for item in value.split(",")]
                geom = Polygon.from_bbox(bbox)
                return queryset.filter(
                    Q(geometry__intersects=geom)
                    | Q(point__within=geom)
                    | Q(monitoring_points__coordinates__within=geom)
                ).distinct()
            except Exception:
                return queryset

    def apply_record_panel_conditions(self, queryset, name, value):
        try:
            record_panel_id = UUID(value)
            record_panel = RecordPanel.objects.get(uuid=record_panel_id)
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.occurrence_record.record_panel_filter_requires_a_valid_existing_uuid"
            )

        filtered_queryset = apply_conditions_to_query(record_panel.conditions, queryset)

        return filtered_queryset

    def get_number_register(self, queryset, name, value: str):
        return queryset.filter(number__icontains=value).distinct()


class OccurrenceRecordOrderingFilter(JSONFieldOrderingFilter):
    def get_order_by_fields(self, request, queryset, view):
        ordering = super().get_order_by_fields(request, queryset, view)

        record_panel_order_present = "record_panel" in ordering
        record_panel_filter_present = "record_panel" in request.query_params

        if record_panel_order_present and record_panel_filter_present:
            record_panel = RecordPanel.objects.get(
                uuid=request.query_params["record_panel"]
            )

            # Extract record_panel list_order_by fields
            order_by_fields = [
                (
                    "{}{}".format(
                        "-" if a["order"] == "DESC" else "",
                        handle_field_name(a["field"]),
                    )
                    if "order" in a
                    else handle_field_name(a["field"])
                )
                for a in record_panel.list_order_by
            ]

            return order_by_fields
        elif record_panel_order_present:
            raise serializers.ValidationError(
                "kartado.error.occurrence_record.ordering_by_record_panel_requires_record_panel_filter"
            )
        else:
            return ordering


class OccurrenceRecordWatcherFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = CharFilter(field_name="occurrence_record__company")
    user = UUIDListFilter()
    firm = UUIDListFilter()

    class Meta:
        model = OccurrenceRecordWatcher
        fields = ["uuid", "user", "firm"]


class RecordPanelFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    viewer_users = UUIDListFilter()
    viewer_firms = UUIDListFilter()
    viewer_permissions = UUIDListFilter()
    editor_users = UUIDListFilter()
    editor_firms = UUIDListFilter()
    editor_permissions = UUIDListFilter()
    created_by = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    conditions = KeyFilter(allow_null=False)
    list_columns = KeyFilter(allow_null=True)
    list_order_by = KeyFilter(allow_null=True)
    kanban_columns = KeyFilter(allow_null=True)
    kanban_group_by = KeyFilter(allow_null=True)
    show_in_list = BooleanFilter(method="get_show_in_list")
    show_in_web_map = BooleanFilter(method="get_show_in_web_map")
    show_in_app_map = BooleanFilter(method="get_show_in_app_map")
    search = CharFilter(label="search", method="get_search")
    menu = ListFilter(allow_null=True)
    has_order = BooleanFilter(method="get_has_order")

    class Meta:
        model = RecordPanel
        fields = [
            "uuid",
            "name",
            "panel_type",
            "conditions",
            "company",
            "viewer_users",
            "viewer_firms",
            "viewer_permissions",
            "editor_users",
            "editor_firms",
            "editor_permissions",
            "list_columns",
            "list_order_by",
            "kanban_columns",
            "kanban_group_by",
            "created_at",
            "created_by",
            "icon",
            "icon_size",
            "color",
            "show_in_list",
            "show_in_web_map",
            "show_in_app_map",
            "menu",
            "has_order",
        ]

    def get_show_in_list(self, queryset, name, value):
        request_user = self.request.user
        if value:
            return queryset.filter(show_in_list_users__in=[request_user])
        else:
            return queryset.exclude(show_in_list_users__in=[request_user])

    def get_show_in_web_map(self, queryset, name, value):
        request_user = self.request.user
        if value:
            return queryset.filter(show_in_web_map_users__in=[request_user])
        else:
            return queryset.exclude(show_in_web_map_users__in=[request_user])

    def get_show_in_app_map(self, queryset, name, value):
        request_user = self.request.user
        if value:
            return queryset.filter(show_in_app_map_users__in=[request_user])
        else:
            return queryset.exclude(show_in_app_map_users__in=[request_user])

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "name",
                Value(" "),
                "panel_type",
                Value(" "),
                output_field=TextField(),
            )
        )
        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def get_has_order(self, queryset, name, value):
        reqs = Q(system_default=True) | Q(panel_order__isnull=False)
        if value:
            return queryset.filter(reqs)
        else:
            return queryset.exclude(reqs)


class CustomDashboardFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    created_by = UUIDListFilter()
    company = UUIDListFilter()
    instrument_types = UUIDListFilter()
    instrument_records = UUIDListFilter()
    sih_monitoring_points = UUIDListFilter()
    can_be_viewed_by = UUIDListFilter()
    can_be_edited_by = UUIDListFilter()
    sih_monitoring_parameters = UUIDListFilter()
    cities = UUIDListFilter()
    operational_positions = KeyFilter(allow_null=False)
    hidro_basins = KeyFilter(allow_null=False)
    plot_descriptions = ListFilter()
    created_at = DateFromToRangeCustomFilter()

    class Meta:
        model = CustomDashboard
        fields = [
            "uuid",
            "name",
            "description",
            "created_at",
            "operational_positions",
            "plot_descriptions",
            "created_by",
            "company",
            "instrument_types",
            "instrument_records",
            "sih_monitoring_points",
            "can_be_viewed_by",
            "can_be_edited_by",
            "sih_monitoring_parameters",
            "hidro_basins",
            "cities",
            "sih_frequency",
        ]


class InstrumentMapFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    instrument_type = UUIDListFilter(field_name="occurrence_type")
    operational_position = ListFilter(
        field_name="form_data__operational_position", allow_null=False
    )

    class Meta:
        model = OccurrenceRecord
        fields = ["uuid", "instrument_type", "operational_position"]


class CustomTableFilter(filters.FilterSet):
    uuid = ListFilter()
    created_by = ListFilter()
    company = ListFilter()
    instrument_records = ListFilter()
    sih_monitoring_points = ListFilter()
    can_be_viewed_by = ListFilter()
    can_be_edited_by = ListFilter()
    cities = ListFilter()
    plot_descriptions = KeyFilter(allow_null=False)
    hidro_basins = KeyFilter(allow_null=False)
    created_at = DateFromToRangeCustomFilter()

    class Meta:
        model = CustomTable
        fields = [
            "uuid",
            "name",
            "description",
            "created_at",
            "created_by",
            "company",
            "instrument_records",
            "sih_monitoring_points",
            "can_be_viewed_by",
            "can_be_edited_by",
            "hidro_basins",
            "cities",
        ]


class TableDataSeriesFilter(filters.FilterSet):
    uuid = ListFilter()
    company = ListFilter()
    instrument_record = ListFilter()
    sih_monitoring_point = ListFilter()
    created_by = ListFilter()
    sih_monitoring_parameter = ListFilter()
    created_at = DateFromToRangeCustomFilter()

    class Meta:
        model = TableDataSeries
        fields = [
            "uuid",
            "name",
            "kind",
            "field_name",
            "company",
            "instrument_record",
            "sih_monitoring_point",
            "created_at",
            "created_by",
            "sih_monitoring_parameter",
            "sih_frequency",
        ]


class DataSeriesFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    instrument_type = UUIDListFilter()
    instrument_record = UUIDListFilter()
    sih_monitoring_point = UUIDListFilter()
    created_by = UUIDListFilter()
    sih_monitoring_parameter = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()
    json_logic = KeyFilter(allow_null=True)

    class Meta:
        model = DataSeries
        fields = [
            "uuid",
            "name",
            "kind",
            "operational_position",
            "field_name",
            "data_type",
            "json_logic",
            "company",
            "instrument_type",
            "instrument_record",
            "sih_monitoring_point",
            "created_at",
            "created_by",
            "sih_monitoring_parameter",
            "sih_frequency",
        ]
