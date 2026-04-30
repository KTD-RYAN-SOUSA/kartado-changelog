from apps.companies.models import Company, Firm
from apps.locations.models import City, Location, River
from apps.monitorings.models import MonitoringPoint
from apps.occurrence_records.models import OccurrenceType
from apps.service_orders.models import ServiceOrderActionStatus
from apps.templates.models import SearchTag
from helpers.apps.record_panel_reporting_fields import get_reporting_fields
from helpers.strings import UF_CODE, get_obj_from_path, to_snake_case

# Corpo hídrico (seleção)
# Equipe do criador (seleção)
# Local (seleção)
# Localidade (seleção)
# Município (seleção)
# Natureza (seleção)
# Origem (seleção)
# Status (seleção)
# UF (seleção)
# Possui serviço? (booleano)
# Serviço foi concluído? (booleano)
# Chave classificatória (seleção)
# Data do registro (data)
# Data de criação (data)
# Nº do Serviço (texto)


class RecordPanelResponse:
    def __init__(self, company: Company, permissions: dict):
        self.response_fields = {}
        self.company = company
        self.permissions = permissions

    def get_list_values(self, queryset, value_prop="uuid", title_prop="name"):
        r = []
        for obj in queryset:
            r.append(
                {
                    "value": (
                        getattr(obj, value_prop)
                        if hasattr(obj, value_prop)
                        else getattr(obj, "id")
                    ),
                    "title": getattr(obj, title_prop),
                }
            )
        return r

    def get_select_field(
        self, queryset, label, name="name", multiple=False, value_prop="uuid"
    ):
        return {
            "label": label,
            "type": "multiselect" if multiple else "select",
            "valueSources": ["value"],
            "fieldSettings": {
                "listValues": self.get_list_values(
                    queryset, value_prop, title_prop=name
                ),
                "allowCustomValues": True,
            },
        }

    def get_boolean_field(self, label):
        return {"label": label, "type": "boolean", "valueSources": ["value"]}

    def get_text_field(self, label):
        return {"label": label, "type": "text", "valueSources": ["value"]}

    def get_date_field(self, label):
        return {"label": label, "type": "date", "valueSources": ["value"]}

    def get_number_field(self, label):
        return {"label": label, "type": "number", "valueSources": ["value"]}

    def get_custom_options_field(self, company, resource, source, label):
        possible_path = "{}__fields__{}__selectoptions__options".format(
            resource, source
        )
        options = get_obj_from_path(company.custom_options, possible_path)
        list_values = [{"value": a["value"], "title": a["name"]} for a in options]

        return {
            "label": label,
            "type": "select",
            "valueSources": ["value"],
            "fieldSettings": {
                "listValues": list_values,
                "allowCustomValues": True,
            },
        }

    def get_monitoring_points(self, company):
        points = MonitoringPoint.objects.filter(
            monitoring_plan__company=company
        ).values_list("uuid", "code")

        list_values = [{"value": a[0], "title": a[1]} for a in points]

        return {
            "label": "Ponto de monitoramento",
            "type": "select",
            "valueSources": ["value"],
            "fieldSettings": {
                "listValues": list_values,
                "allowCustomValues": True,
            },
        }

    def get_parameter_groups(self, company):
        groups = OccurrenceType.objects.filter(
            monitoring_plan__company=company
        ).values_list("uuid", "name")

        list_values = [{"value": a[0], "title": a[1]} for a in groups]

        return {
            "label": "Grupo de parâmetro",
            "type": "select",
            "valueSources": ["value"],
            "fieldSettings": {
                "listValues": list_values,
                "allowCustomValues": True,
            },
        }

    def get_response(self) -> dict:
        return self.response_fields


class OccurrenceRecordsResponse(RecordPanelResponse):
    def __init__(self, company_id, permissions) -> None:
        super().__init__(company_id, permissions)
        self.generate_occurrence_record_fields()

    def generate_occurrence_record_fields(self):
        company = Company.objects.get(uuid=self.company.uuid)

        # TODO: Replace with authorized querysets
        rivers = River.objects.filter(company=company)
        firms = Firm.objects.filter(company=company)
        locations = Location.objects.filter(company=company)
        cities = City.objects.all()
        statuses = ServiceOrderActionStatus.objects.filter(
            companies=company, kind="OCCURRENCE_RECORD_STATUS"
        )
        search_tags = SearchTag.objects.filter(company=company)
        occurrence_kind = SearchTag.objects.filter(company=company, level=3)

        self.response_fields["river"] = self.get_select_field(rivers, "Corpo hídrico")
        self.response_fields["firm"] = self.get_select_field(firms, "Equipe do criador")
        self.response_fields["place_on_dam"] = self.get_custom_options_field(
            company, "occurrenceRecord", "placeOnDam", "Local"
        )
        self.response_fields["location"] = self.get_select_field(
            locations, "Localidade"
        )
        self.response_fields["city"] = self.get_select_field(cities, "Município")
        self.response_fields["kind_tag_id"] = self.get_select_field(
            occurrence_kind, "Natureza"
        )
        self.response_fields["origin"] = self.get_custom_options_field(
            company, "occurrenceRecord", "origin", "Origem"
        )
        self.response_fields["status"] = self.get_select_field(statuses, "Status")
        self.response_fields["uf_code"] = {
            "label": "Código UF",
            "type": "select",
            "valueSources": ["value"],
            "fieldSettings": {
                "listValues": [{"value": a[0], "title": a[1]} for a in UF_CODE.items()],
                "allowCustomValues": False,
            },
        }
        self.response_fields["has_service"] = self.get_boolean_field("Possui serviço?")
        self.response_fields["service_is_done"] = self.get_boolean_field(
            "Serviço foi concluído?"
        )
        self.response_fields["search_tag"] = self.get_select_field(
            search_tags, "Chave classificatória"
        )
        self.response_fields["record_tag_id"] = self.get_select_field(
            search_tags, "Registro"
        )
        self.response_fields["type_tag_id"] = self.get_select_field(search_tags, "Tipo")
        self.response_fields["subject_tag_id"] = self.get_select_field(
            search_tags, "Assunto"
        )

        self.response_fields["datetime"] = self.get_date_field("Data do registro")
        self.response_fields["created_at"] = self.get_date_field("Data de criação")
        self.response_fields["number"] = self.get_text_field("Nº Registro")

        self.response_fields["monitoring_points"] = self.get_monitoring_points(company)
        self.response_fields["parameter_group"] = self.get_parameter_groups(company)

        company_types = OccurrenceType.objects.filter(company=company)

        for occurrence_type in company_types:
            for field in occurrence_type.form_fields["fields"]:
                api_name = "form_data." + get_obj_from_path(field, "apiname")
                display_name = get_obj_from_path(field, "displayname")
                data_type = get_obj_from_path(field, "datatype")
                if data_type == "boolean":
                    self.response_fields[
                        to_snake_case(api_name)
                    ] = self.get_boolean_field(display_name)
                elif (
                    data_type == "string"
                    or data_type == "textArea"
                    or data_type == "text_area"
                ):
                    self.response_fields[to_snake_case(api_name)] = self.get_text_field(
                        display_name
                    )
                elif data_type == "timestamp":
                    self.response_fields[to_snake_case(api_name)] = self.get_date_field(
                        display_name
                    )
                elif data_type == "number" or data_type == "float":
                    self.response_fields[
                        to_snake_case(api_name)
                    ] = self.get_number_field(display_name)
                elif data_type == "select":
                    select_options = get_obj_from_path(field, "select_options__options")
                    if select_options:
                        self.response_fields[to_snake_case(api_name)] = {
                            "label": display_name,
                            "type": "select",
                            "valueSources": ["value"],
                            "fieldSettings": {
                                "listValues": [
                                    {"value": a["value"], "title": a["name"]}
                                    for a in select_options
                                ],
                                "allowCustomValues": True,
                            },
                        }
                elif data_type == "select_multiple" or data_type == "selectMultiple":
                    select_options = get_obj_from_path(field, "select_options__options")
                    if select_options:
                        self.response_fields[to_snake_case(api_name)] = {
                            "label": display_name,
                            "type": "multiselect",
                            "valueSources": ["value"],
                            "fieldSettings": {
                                "listValues": [
                                    {"value": a["value"], "title": a["name"]}
                                    for a in select_options
                                ],
                                "allowCustomValues": True,
                            },
                        }

        # Sort results
        for field_data in self.response_fields.values():
            list_values = get_obj_from_path(field_data, "fieldsettings__listvalues")
            if list_values:
                list_values.sort(key=lambda item: item["title"])


class ReportingResponse(RecordPanelResponse):
    def __init__(self, company: Company, permissions: dict):
        super().__init__(company, permissions)
        self.reporting_fields = get_reporting_fields(company)
        self.set_custom_option_select_fields()
        self.set_default_select_fields()
        self.set_boolean_fields()
        self.set_date_fields()
        self.set_number_fields()
        self.set_text_fields()
        self.set_occurrence_type_fields()

    @property
    def number_fields(self) -> dict:
        return self.reporting_fields["number_fields"]

    @property
    def date_fields(self) -> dict:
        return self.reporting_fields["date_fields"]

    @property
    def boolean_fields(self) -> dict:
        return self.reporting_fields["boolean_fields"]

    @property
    def text_fields(self) -> dict:
        return self.reporting_fields["text_fields"]

    @property
    def default_select_fields(self) -> list:
        return self.reporting_fields["select_fields"]["default_select_fields"]

    @property
    def custom_option_fields(self) -> list:
        return self.reporting_fields["select_fields"]["custom_option_fields"]

    def set_custom_option_select_fields(self):
        for meta_data in self.custom_option_fields:
            if not self.check_permissions(
                meta_data["company_permissions"], meta_data["user_permissions"]
            ):
                continue
            self.response_fields[
                meta_data["field_name"]
            ] = self.get_custom_options_field(
                self.company,
                "reporting",
                meta_data["source"],
                meta_data["label"],
            )

    def check_permissions(
        self, company_permissions: list, user_permissions: list
    ) -> bool:
        """
        If the permissions list is empty, there is no need to check the permission.
        """
        has_all_company_permissions = (
            True
            if not company_permissions
            else self.check_company_permissions(company_permissions)
        )
        has_all_user_permissions = (
            True
            if not user_permissions
            else self.check_user_permissions(user_permissions)
        )
        return has_all_company_permissions and has_all_user_permissions

    def set_default_select_fields(self) -> None:
        for select_field_data in self.default_select_fields:
            if not self.check_permissions(
                select_field_data["company_permissions"],
                select_field_data["user_permissions"],
            ):
                continue
            name = select_field_data.get("name")
            value_prop = select_field_data.get("value_prop")
            self.response_fields[
                select_field_data["field_name"]
            ] = self.get_select_field(
                queryset=select_field_data["queryset"],
                label=select_field_data["label"],
                name=name if name else "name",
                value_prop=value_prop if value_prop else "uuid",
            )

    def set_boolean_fields(self):
        for boolean_field_metadata in self.boolean_fields:
            if not self.check_permissions(
                boolean_field_metadata["company_permissions"],
                boolean_field_metadata["user_permissions"],
            ):
                continue
            self.response_fields[
                boolean_field_metadata["field_name"]
            ] = self.get_boolean_field(boolean_field_metadata["label"])

    def set_number_fields(self):
        for number_field_metadata in self.number_fields:
            if not self.check_permissions(
                number_field_metadata["company_permissions"],
                number_field_metadata["user_permissions"],
            ):
                continue
            self.response_fields[
                number_field_metadata["field_name"]
            ] = self.get_number_field(number_field_metadata["label"])

    def set_date_fields(self):
        for date_field_metadata in self.date_fields:
            if not self.check_permissions(
                date_field_metadata["company_permissions"],
                date_field_metadata["user_permissions"],
            ):
                continue
            self.response_fields[
                date_field_metadata["field_name"]
            ] = self.get_date_field(date_field_metadata["label"])

    def set_text_fields(self):
        for text_field_metadata in self.text_fields:
            if not self.check_permissions(
                text_field_metadata["company_permissions"],
                text_field_metadata["user_permissions"],
            ):
                continue
            self.response_fields[
                text_field_metadata["field_name"]
            ] = self.get_text_field(text_field_metadata["label"])

    def set_occurrence_type_fields(self):
        company_types = OccurrenceType.objects.filter(company=self.company)

        for occurrence_type in company_types:
            if "fields" in occurrence_type.form_fields:
                for field in occurrence_type.form_fields["fields"]:
                    api_name = "form_data." + get_obj_from_path(field, "apiname")
                    display_name = get_obj_from_path(field, "displayname")
                    data_type = get_obj_from_path(field, "datatype")
                    if data_type == "boolean":
                        self.response_fields[
                            to_snake_case(api_name)
                        ] = self.get_boolean_field(display_name)
                    elif (
                        data_type == "string"
                        or data_type == "textArea"
                        or data_type == "text_area"
                    ):
                        self.response_fields[
                            to_snake_case(api_name)
                        ] = self.get_text_field(display_name)
                    elif data_type == "timestamp":
                        self.response_fields[
                            to_snake_case(api_name)
                        ] = self.get_date_field(display_name)
                    elif data_type == "number" or data_type == "float":
                        self.response_fields[
                            to_snake_case(api_name)
                        ] = self.get_number_field(display_name)
                    elif data_type == "select":
                        select_options = get_obj_from_path(
                            field, "select_options__options"
                        )
                        if select_options:
                            self.response_fields[to_snake_case(api_name)] = {
                                "label": display_name,
                                "type": "select",
                                "valueSources": ["value"],
                                "fieldSettings": {
                                    "listValues": [
                                        {"value": a["value"], "title": a["name"]}
                                        for a in select_options
                                    ],
                                    "allowCustomValues": True,
                                },
                            }
                    elif (
                        data_type == "select_multiple" or data_type == "selectMultiple"
                    ):
                        select_options = get_obj_from_path(
                            field, "select_options__options"
                        )
                        if select_options:
                            self.response_fields[to_snake_case(api_name)] = {
                                "label": display_name,
                                "type": "multiselect",
                                "valueSources": ["value"],
                                "fieldSettings": {
                                    "listValues": [
                                        {"value": a["value"], "title": a["name"]}
                                        for a in select_options
                                    ],
                                    "allowCustomValues": True,
                                },
                            }

    def check_user_permissions(self, user_permissions) -> bool:
        for user_permission_data in user_permissions:
            try:
                permission = get_obj_from_path(
                    self.permissions, user_permission_data["model"]
                )
                if not isinstance(permission, dict):
                    return False
                permission = permission.get(user_permission_data["permission"], False)
                if permission is False:
                    return False
            except Exception:
                return False
        return True

    def check_company_permissions(self, company_permissions: dict) -> bool:
        for permission_data in company_permissions:
            permission = (
                get_obj_from_path(self.company.metadata, permission_data["permission"])
                or False
            )
            if not isinstance(permission, bool):
                return False
            # In some cases, if permission is false, the value is set as true, like "hide_reporting_location"
            permission = (
                not (permission) if permission_data["reverse"] is True else permission
            )
            if not permission:
                return False
        return True


def get_response(company: Company, permissions: dict):
    reporting_permission, occurrence_record_permission = False, False
    try:
        reporting_permission = permissions["reporting"]["can_view"][0]
    except Exception:
        pass
    if reporting_permission is True:
        reporting_response = ReportingResponse(company, permissions)
        return reporting_response.get_response()
    try:
        occurrence_record_permission = permissions["occurrence_record"]["can_view"][0]
    except Exception:
        pass
    if occurrence_record_permission is True:
        occ_record_response = OccurrenceRecordsResponse(company, permissions)
        return occ_record_response.get_response()
    return {}
