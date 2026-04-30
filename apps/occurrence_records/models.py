import uuid
from datetime import datetime, timedelta

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.db.models import JSONField, QuerySet
from simple_history.models import HistoricalRecords

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company, Firm, SubCompany
from apps.files.models import File
from apps.integrations.models import IntegrationRun
from apps.locations.models import City, Location, River
from apps.maps.models import ShapeFile, TileLayer
from apps.monitorings.models import MonitoringPlan, MonitoringPoint, OperationalControl
from apps.occurrence_records.const.sih_frequencies import SIH_FREQUENCIES
from apps.occurrence_records.helpers.methods.altimetry_methods import AltimetryMethods
from apps.permissions.models import UserPermission
from apps.service_orders.models import (
    ServiceOrder,
    ServiceOrderAction,
    ServiceOrderActionStatus,
)
from apps.users.models import User
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.record_filter import create_involved_parts_keywords, create_keywords
from helpers.fields import ColorField
from helpers.forms import form_fields_dict
from helpers.models import HashHistoricalModel
from helpers.serializers import get_obj_serialized
from helpers.strings import get_obj_from_path, keys_to_snake_case, to_snake_case

from .const import custom_table, data_series_kinds
from .const.panel_types import PANEL_TYPES


class OccurrenceType(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.TextField()
    company = models.ManyToManyField(
        Company,
        through="OccurrenceTypeSpecs",
        related_name="occurrence_type_companies",
    )
    firms = models.ManyToManyField(Firm, related_name="occurrence_type_firms")
    occurrence_kind = models.CharField(max_length=200, blank=True)
    form_fields = JSONField(default=dict, blank=True, null=True)
    goal_formula = JSONField(default=list, blank=True, null=True)

    monitoring_plan = models.ForeignKey(
        MonitoringPlan,
        on_delete=models.SET_NULL,
        related_name="occurrence_types_plan",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    deadline = models.DurationField(null=True, blank=True)

    active = models.BooleanField(default=True)
    previous_version = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="next_version",
    )

    show_in_web_map = models.BooleanField(default=True)
    show_in_app_map = models.BooleanField(default=True)
    icon = models.TextField(default="", blank=True, null=True)
    icon_size = models.IntegerField(default=15, blank=True, null=True)
    color = models.CharField(max_length=100, default="#005dffb3", blank=True, null=True)
    custom_map_table = JSONField(default=list, blank=True)

    is_oae = models.BooleanField(default=False)
    repetition = JSONField(default=dict, blank=True, null=True)

    history = HistoricalRecords()

    def __str__(self):
        companies_names = [comp.name for comp in self.company.all()]
        return "{} - {}".format(self.name, companies_names)

    @property
    def get_company_id(self):
        return self.company.first().uuid


class OccurrenceTypeSpecs(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Required
    occurrence_type = models.ForeignKey(
        OccurrenceType,
        on_delete=models.CASCADE,
        related_name="occurrencetype_specs",
    )
    # Required
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_specs"
    )

    color = ColorField(default="#FF0000")
    has_no_flow = models.BooleanField(default=False)
    is_not_listed = models.BooleanField(default=False)
    is_not_notified = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}".format(self.occurrence_type.name, self.company.name)

    class Meta:
        unique_together = ("company", "occurrence_type")

    @property
    def get_company_id(self):
        return self.company_id


class OccurrenceRecord(models.Model, AltimetryMethods):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic Information
    datetime = models.DateTimeField(blank=True, null=True)
    number = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviews = models.IntegerField(default=0)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    editable = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)

    # Location
    uf_code = models.IntegerField(blank=True, null=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, blank=True, null=True)
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, blank=True, null=True
    )
    place_on_dam = models.CharField(max_length=100, blank=True)
    river = models.ForeignKey(River, on_delete=models.SET_NULL, blank=True, null=True)
    point = models.PointField(null=True, blank=True)
    geometry = models.GeometryCollectionField(null=True, blank=True)
    properties = JSONField(default=list, blank=True)
    distance_from_dam = models.FloatField(default=0)
    other_reference = models.TextField(blank=True)

    # Occurence Record Origin
    origin = models.CharField(max_length=200, blank=True, null=True)
    origin_media = models.CharField(max_length=200, blank=True, null=True)
    informer = JSONField(default=dict, blank=True, null=True)

    # Territorial Administration
    territorial_administration = models.CharField(max_length=200, blank=True)

    # Registerer
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="records_created",
        null=True,
    )

    # SearchTag fields
    search_tags = models.ManyToManyField(
        "templates.SearchTag", related_name="occurrence_records", blank=True
    )
    search_tag_description = models.CharField(max_length=255, blank=True)
    record_tag_id = models.TextField(null=True)
    record_tag = models.TextField(null=True)
    record = models.TextField(null=True)
    type_tag_id = models.TextField(null=True)
    type_tag = models.TextField(null=True)
    type = models.TextField(null=True)
    kind_tag_id = models.TextField(null=True)
    kind = models.TextField(null=True)
    subject_tag_id = models.TextField(null=True)
    subject = models.TextField(null=True)

    # Occurrence Info
    occurrence_type = models.ForeignKey(
        OccurrenceType,
        on_delete=models.SET_NULL,
        null=True,
        related_name="type_records",
    )
    form_data = JSONField(default=dict, blank=True, null=True)
    form_metadata = JSONField(default=dict, blank=True, null=True)
    arcgis_ids = JSONField(default=dict, blank=True, null=True)

    status = models.ForeignKey(
        ServiceOrderActionStatus,
        on_delete=models.SET_NULL,
        related_name="status_records",
        null=True,
    )

    service_orders = models.ManyToManyField(
        ServiceOrder, related_name="so_records", blank=True
    )

    operational_control = models.ForeignKey(
        OperationalControl,
        on_delete=models.CASCADE,
        related_name="op_control_records",
        null=True,
        blank=True,
    )

    monitoring_plan = models.ForeignKey(
        MonitoringPlan,
        on_delete=models.CASCADE,
        related_name="monitoring_records",
        null=True,
        blank=True,
    )

    parent_action = models.ForeignKey(
        ServiceOrderAction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_records",
    )

    firm = models.ForeignKey(
        Firm,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="firm_records",
    )

    responsible = models.ForeignKey(
        User,
        related_name="responsible_records",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    monitoring_points = models.ManyToManyField(
        MonitoringPoint, related_name="points_records", blank=True
    )

    keywords = models.TextField(default="", null=True)
    approval_step = models.ForeignKey(
        ApprovalStep,
        on_delete=models.SET_NULL,
        related_name="step_records",
        null=True,
        blank=True,
    )
    involved_parts = JSONField(default=list, blank=True, null=True)
    involved_parts_keywords = models.TextField(default="", null=True)

    # Map
    active_shape_files = models.ManyToManyField(
        ShapeFile, related_name="shape_file_records", blank=True
    )
    active_tile_layer = models.ForeignKey(
        TileLayer,
        on_delete=models.SET_NULL,
        related_name="tyle_layer_records",
        null=True,
        blank=True,
    )

    # File
    file = GenericRelation(File, related_query_name="record_file")

    # Integration
    integration_run = models.ForeignKey(
        IntegrationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="records",
    )

    # Validation
    validation_deadline = models.DateTimeField(blank=True, null=True)
    validated_at = models.DateTimeField(blank=True, null=True)

    # Linked occurrence records
    main_linked_record = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="main_link_records",
    )
    other_linked_records = models.ManyToManyField(
        "self", related_name="link_records", blank=True
    )

    history = HistoricalRecords(
        bases=[HashHistoricalModel],
        history_change_reason_field=models.TextField(null=True),
        related_name="historicaloccurrencerecord",
    )

    def __str__(self):
        return "[{}] - {} - {}".format(self.company.name, self.number, self.datetime)

    def save(self, *args, **kwargs):
        # Refresh keywords
        if self.form_data and self.occurrence_type:
            self.keywords = create_keywords(self.form_data, self.occurrence_type)

        # Refresh involved_parts_keywords
        if self.involved_parts:
            self.involved_parts_keywords = create_involved_parts_keywords(
                self.company, self.involved_parts
            )

        for _ in range(3):
            obj_serialized = get_obj_serialized(self, is_occurrence_record=True)

            if obj_serialized:
                form_fields = form_fields_dict(self.occurrence_type)
                for field_name in form_fields.keys():
                    snake_field_name = to_snake_case(field_name)
                    if snake_field_name not in self.form_metadata:
                        self.form_metadata[snake_field_name] = {
                            "manually_specified": False
                        }

                for key, value in self.form_metadata.items():
                    manually_specified = get_obj_from_path(value, "manually_specified")
                    if isinstance(manually_specified, bool) and not manually_specified:
                        # use get_obj_from_path here to avoid crashes
                        # when key gets here in snake_case but field name is camelCase
                        # If unable to get form_field or unable to compute jsonLogic, don't crash
                        form_field = get_obj_from_path(form_fields, key)
                        if isinstance(form_field, dict):
                            autofill = form_field.get("autofill")
                            if autofill:
                                try:
                                    self.form_data[key] = apply_json_logic(
                                        autofill,
                                        obj_serialized,
                                        self.occurrence_type,
                                        self.company,
                                    )
                                except Exception:
                                    pass

        super(OccurrenceRecord, self).save(*args, **kwargs)

    def get_main_property(self, shape_file_property: str = "") -> dict:
        try:
            form_data = self.form_data

            if not shape_file_property:
                shape_file_property = form_data.get("shape_file_property", None)

            property_intersections = form_data.get("property_intersections", None)
            if property_intersections:
                for main_property in property_intersections:
                    if main_property["attributes"]["uuid"] == shape_file_property:
                        return main_property
        except Exception:
            return

    def get_place_on_dam_display(self):
        custom_options = keys_to_snake_case(self.company.custom_options)
        occurrence_record_local = ""
        if custom_options.get("occurrence_record", None) and custom_options.get(
            "occurrence_record"
        ).get("fields", None):
            occurrence_record_fields = keys_to_snake_case(
                custom_options.get("occurrence_record").get("fields")
            )
            if occurrence_record_fields.get("place_on_dam", None):
                place_on_dam = keys_to_snake_case(
                    occurrence_record_fields.get("place_on_dam")
                )
                for option in place_on_dam.get("select_options").get("options"):
                    if self.place_on_dam == option["value"]:
                        occurrence_record_local = option.get("name", "")
                        break

        return occurrence_record_local

    def get_occurrence_kind_display(self):
        custom_options = keys_to_snake_case(self.company.custom_options)
        occurrence_record_kind = ""
        options = get_obj_from_path(
            custom_options,
            "occurrencerecord__fields__occurrencekind__selectoptions__options",
        )

        for option in options:
            if (
                self.occurrence_type
                and self.occurrence_type.occurrence_kind == option["value"]
            ):
                occurrence_record_kind = option.get("name", "")
                break

        return occurrence_record_kind

    def get_offender_name(self):
        offender_name = ""
        for involved in self.involved_parts:
            if involved["involved_parts"] == "1":
                offender_name = involved["name"]
                break

        return offender_name

    def get_levels(self) -> QuerySet:
        try:
            return self.search_tags.order_by("level")
        except Exception:
            return

    @property
    def get_company_id(self):
        return self.company_id


class OccurrenceRecordWatcher(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Required
    occurrence_record = models.ForeignKey(
        OccurrenceRecord,
        on_delete=models.CASCADE,
        related_name="occurrencerecord_watchers",
    )
    # Required
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_watchers",
        blank=True,
        null=True,
    )

    firm = models.ForeignKey(
        Firm,
        on_delete=models.CASCADE,
        related_name="firm_watchers",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_watchers",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="updated_watchers",
        null=True,
        blank=True,
    )
    status_email = models.BooleanField(default=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}".format(
            self.occurrence_record.number, self.occurrence_record.company.name
        )

    @property
    def get_company_id(self):
        return self.occurrence_record.company_id


class RecordPanel(models.Model):
    """Painél Personalizado"""

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic info
    name = models.TextField()
    panel_type = models.CharField(choices=PANEL_TYPES, max_length=6)
    conditions = JSONField(default=dict)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_record_panels"
    )

    # Viewers
    viewer_users = models.ManyToManyField(
        User, related_name="record_panels_viewer", blank=True
    )
    viewer_firms = models.ManyToManyField(
        Firm, related_name="record_panels_viewer", blank=True
    )
    viewer_permissions = models.ManyToManyField(
        UserPermission, related_name="record_panels_viewer", blank=True
    )
    viewer_subcompanies = models.ManyToManyField(
        SubCompany, related_name="record_panels_viewer", blank=True
    )

    # Editors
    editor_users = models.ManyToManyField(
        User, related_name="record_panels_editor", blank=True
    )
    editor_firms = models.ManyToManyField(
        Firm, related_name="record_panels_editor", blank=True
    )
    editor_permissions = models.ManyToManyField(
        UserPermission, related_name="record_panels_editor", blank=True
    )
    editor_subcompanies = models.ManyToManyField(
        SubCompany, related_name="record_panels_editor", blank=True
    )

    # LIST Panel
    list_columns = JSONField(default=list, blank=True, null=True)
    list_order_by = JSONField(default=list, blank=True, null=True)

    # KANBAN Panel
    kanban_columns = JSONField(default=list, blank=True, null=True)
    kanban_group_by = JSONField(default=list, blank=True, null=True)

    show_in_list_users = models.ManyToManyField(
        User,
        through="occurrence_records.RecordPanelShowList",
        blank=True,
        related_name="show_list_record_panels",
    )
    show_in_web_map_users = models.ManyToManyField(
        User,
        through="occurrence_records.RecordPanelShowWebMap",
        blank=True,
        related_name="show_web_map_record_panels",
    )
    show_in_app_map_users = models.ManyToManyField(
        User,
        through="occurrence_records.RecordPanelShowMobileMap",
        blank=True,
        related_name="show_app_map_record_panels",
    )

    # Appearance
    icon = models.TextField(blank=True, null=True)
    icon_size = models.IntegerField(default=15)
    color = models.CharField(max_length=100, default="#005dffb3")

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_record_panels",
        null=True,
        blank=True,
    )
    limit = models.Q(
        app_label="occurrence_records", model="occurrencerecord"
    ) | models.Q(app_label="reportings", model="reporting")
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        limit_choices_to=limit,
    )
    menu = models.ForeignKey(
        "reportings.RecordMenu",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="menu_record_panels",
    )
    system_default = models.BooleanField(default=False)

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {} - {}".format(self.company.name, self.uuid, self.name)


class RecordPanelShowList(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    panel = models.ForeignKey(
        RecordPanel, on_delete=models.CASCADE, related_name="panel_show_lists"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_show_lists"
    )
    order = models.IntegerField()
    new_to_user = models.BooleanField(default=False)

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.panel.company_id

    class Meta:
        unique_together = ["panel", "user"]
        ordering = ["panel__company"]

    def __str__(self):
        return "[{}] {} - {}".format(
            self.panel.company.name, self.uuid, self.panel.name
        )


class RecordPanelShowWebMap(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    panel = models.ForeignKey(
        RecordPanel,
        on_delete=models.CASCADE,
        related_name="panel_show_web_maps",
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_show_web_maps"
    )

    @property
    def get_company_id(self):
        return self.panel.company_id

    class Meta:
        unique_together = ["panel", "user"]
        ordering = ["panel__company"]

    def __str__(self):
        return "[{}] {} - {}".format(
            self.panel.company.name, self.uuid, self.panel.name
        )


class RecordPanelShowMobileMap(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    panel = models.ForeignKey(
        RecordPanel,
        on_delete=models.CASCADE,
        related_name="panel_show_mobile_maps",
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_show_mobile_maps"
    )

    @property
    def get_company_id(self):
        return self.panel.company_id

    class Meta:
        unique_together = ["panel", "user"]
        ordering = ["panel__company"]

    def __str__(self):
        return "[{}] {} - {}".format(
            self.panel.company.name, self.uuid, self.panel.name
        )


class CustomDashboard(models.Model):
    """Indicador Personalizado"""

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic info
    name = models.TextField()
    description = models.TextField()
    operational_positions = JSONField(default=dict, blank=True, null=True)
    plot_descriptions = JSONField(default=list, blank=True, null=True)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_dashboards"
    )
    instrument_types = models.ManyToManyField(
        OccurrenceType, related_name="occurrence_type_dashboards", blank=True
    )
    instrument_records = models.ManyToManyField(
        OccurrenceRecord,
        related_name="occurrence_record_dashboards",
        blank=True,
    )
    sih_monitoring_points = models.ManyToManyField(
        OccurrenceRecord,
        related_name="occurrence_record_sih_monitoring_points_dashboards",
        blank=True,
    )

    # Water resources
    sih_monitoring_parameters = models.ManyToManyField(
        OccurrenceRecord,
        "occurrence_record_sih_monitoring_parameters",
        blank=True,
    )
    hidro_basins = JSONField(default=list, blank=True, null=True)
    cities = models.ManyToManyField(
        City,
        "city_custom_dashboards",
        blank=True,
    )
    sih_frequency = models.CharField(
        blank=True,
        null=True,
        max_length=7,
        choices=SIH_FREQUENCIES,
    )
    start_date_hydrological_parameters = models.DateField(null=True, blank=True)
    end_date_hydrological_parameters = models.DateField(null=True, blank=True)

    # Viewers & editors
    can_be_viewed_by = models.ManyToManyField(
        User, "user_dashboards_viewer", blank=True
    )
    can_be_edited_by = models.ManyToManyField(
        User, "user_dashboards_editor", blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_dashboards",
        null=True,
        blank=True,
    )

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {} - {}".format(self.company.name, self.uuid, self.name)


class DataSeries(models.Model):
    """Série Histórica"""

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic Info
    name = models.TextField()
    kind = models.CharField(
        max_length=14,
        choices=data_series_kinds.DATA_SERIES_KINDS,
        default=data_series_kinds.SERIES_KIND,
    )
    operational_position = models.TextField()
    field_name = models.TextField()
    data_type = models.TextField()
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_data_series"
    )
    instrument_type = models.ForeignKey(
        OccurrenceType,
        on_delete=models.SET_NULL,
        related_name="occurrence_type_data_series",
        null=True,
        blank=True,
    )
    instrument_record = models.ForeignKey(
        OccurrenceRecord,
        on_delete=models.SET_NULL,
        related_name="occurrence_record_data_series",
        null=True,
        blank=True,
    )
    sih_monitoring_point = models.ForeignKey(
        OccurrenceRecord,
        on_delete=models.SET_NULL,
        related_name="occurrence_record_sih_monitoring_point_data_series",
        null=True,
        blank=True,
    )
    json_logic = JSONField(default=dict, blank=True, null=True)
    sih_monitoring_parameter = models.ForeignKey(
        OccurrenceRecord,
        on_delete=models.SET_NULL,
        related_name="occurrence_record_sih_parameters",
        null=True,
        blank=True,
    )

    # Creation Info
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_data_series",
        null=True,
        blank=True,
    )

    sih_frequency = models.CharField(
        blank=True,
        null=True,
        max_length=20,
        choices=SIH_FREQUENCIES,
    )  # This field must be required only when the DataSeries kind is SIH

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {} - {}".format(self.company.name, self.uuid, self.name)


class CustomTable(models.Model):
    """Tabela Personalizado"""

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_tables"
    )

    # Basic info
    name = models.TextField()
    description = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_tables",
        null=True,
        blank=True,
    )

    # Viewers & editors
    can_be_viewed_by = models.ManyToManyField(User, "user_tables_viewer", blank=True)
    can_be_edited_by = models.ManyToManyField(User, "user_tables_editor", blank=True)

    # Table info

    _start_period = models.DateField(
        null=True,
        blank=True,
    )
    _end_period = models.DateField(
        null=True,
        blank=True,
    )

    # ----- Customização: Geral 4 ----- #

    dynamic_period_in_days = models.IntegerField(
        null=True,
        blank=True,
    )

    # ----- Customização: Geral 4 ----- #

    table_type = models.CharField(
        max_length=10,
        choices=custom_table.CUSTOM_TABLE_TYPES,
        default=custom_table.ANALYSIS,
    )

    columns_break = models.CharField(
        max_length=10,
        choices=custom_table.CUSTOM_TABLE_COLUMN_BREAKS,
        default=custom_table.DAY,
    )

    line_frequency = models.CharField(
        blank=True,
        null=True,
        max_length=7,
        choices=SIH_FREQUENCIES,
    )

    hidro_basins = JSONField(default=list, blank=True, null=True)
    cities = models.ManyToManyField(
        City,
        "custom_tables",
        blank=True,
    )
    instrument_records = models.ManyToManyField(
        OccurrenceRecord,
        related_name="occurrence_record_tables",
        blank=True,
    )
    sih_monitoring_points = models.ManyToManyField(
        OccurrenceRecord,
        related_name="occurrence_record_sih_monitoring_points_record_tables",
        blank=True,
    )
    table_data_series = models.ManyToManyField(
        "occurrence_records.TableDataSeries",
        "custom_tables",
        blank=True,
    )

    additional_columns = JSONField(default=list, blank=True, null=True)
    additional_lines = JSONField(default=list, blank=True, null=True)

    table_descriptions = JSONField(default=dict, blank=True, null=True)

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    @property
    def start_period(self) -> datetime:
        if self.dynamic_period_in_days:
            return datetime.now() - timedelta(days=self.dynamic_period_in_days)
        return self._start_period

    @start_period.setter
    def start_period(self, value: datetime):
        self._start_period = value

    @property
    def end_period(self) -> datetime:
        if self.dynamic_period_in_days:
            return datetime.now()
        return self._end_period

    @end_period.setter
    def end_period(self, value: datetime):
        self._end_period = value

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {} - {}".format(self.company.name, self.uuid, self.name)

    def clean(self) -> None:

        if self._start_period and self._end_period:
            self.dynamic_period_in_days = None
        elif self.dynamic_period_in_days:
            self._start_period = None
            self._end_period = None

        return super().clean()


class TableDataSeries(models.Model):
    """Série Histórica para tabelas"""

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic Info
    name = models.TextField()
    kind = models.CharField(
        max_length=14,
        choices=data_series_kinds.DATA_SERIES_KINDS,
        default=data_series_kinds.SERIES_KIND,
    )
    field_name = models.TextField()
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="company_table_data_series",
    )
    instrument_record = models.ForeignKey(
        OccurrenceRecord,
        on_delete=models.SET_NULL,
        related_name="occurrence_record_table_data_series",
        null=True,
        blank=True,
    )
    sih_monitoring_point = models.ForeignKey(
        OccurrenceRecord,
        on_delete=models.SET_NULL,
        related_name="occurrence_record_sih_monitoring_point_table_data_series",
        null=True,
        blank=True,
    )
    sih_monitoring_parameter = models.ForeignKey(
        OccurrenceRecord,
        on_delete=models.SET_NULL,
        related_name="occurrence_record_sih_parameters_table_data_series",
        null=True,
        blank=True,
    )

    # Creation Info
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_table_data_series",
        null=True,
        blank=True,
    )

    sih_frequency = models.CharField(
        blank=True,
        null=True,
        max_length=20,
        choices=SIH_FREQUENCIES,
    )  # This field must be required only when the DataSeries kind is SIH

    history = HistoricalRecords()

    @property
    def get_company_id(self):
        return self.company_id

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return "[{}] {} - {}".format(self.company.name, self.uuid, self.name)
