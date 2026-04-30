from django.conf import settings
from django.core.validators import EMPTY_VALUES

from apps.daily_reports.const.occurrence_origin import (
    TRANSLATE_OCCURRENCE_ORIGIN_CHOICES,
)
from apps.daily_reports.models import (
    DailyReportEquipment,
    DailyReportOccurrence,
    DailyReportResource,
    DailyReportSignaling,
    DailyReportVehicle,
    DailyReportWorker,
)
from apps.occurrence_records.models import OccurrenceType
from helpers.apps.daily_reports import (
    format_km,
    get_km_intervals_field,
    translate_condition,
    translate_weather,
)
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.reportings import return_array_values, return_select_value
from helpers.dates import format_date, utc_to_local
from helpers.serializers import get_obj_serialized
from helpers.strings import get_obj_from_path, to_flatten_str, to_snake_case


class SpreadsheetEndpoint:
    def __init__(self, queryset, company, include_city=False):
        self.queryset = queryset
        self.company = company
        self.include_city = include_city
        self.reference_values = {
            str(a.uuid): a.name
            for a in OccurrenceType.objects.filter(company=self.company).only(
                "name", "uuid"
            )
        }

    def get_data(self):
        data = []
        for reporting in self.queryset:
            # basics
            uuid = str(reporting.uuid)
            number = reporting.number or ""
            road_name = reporting.road_name or ""
            km = reporting.km
            end_km = reporting.end_km or km
            url = "{}/#/SharedLink/Reporting/{}/show?company={}".format(
                settings.FRONTEND_URL, str(reporting.uuid), str(self.company.uuid)
            )

            # relationships
            occ_type = (
                getattr(reporting.occurrence_type, "name", "")
                if reporting.occurrence_type
                else ""
            )
            status = getattr(reporting.status, "name", "") if reporting.status else ""
            created_by = (
                reporting.created_by.get_full_name() if reporting.created_by else ""
            )
            firm = getattr(reporting.firm, "name", "") if reporting.firm else ""
            subcompany = (
                getattr(reporting.firm.subcompany, "name", "")
                if reporting.firm and reporting.firm.subcompany
                else ""
            )
            job = getattr(reporting.job, "title", "") if reporting.job else ""
            construction = (
                getattr(reporting.construction, "name", "")
                if reporting.construction
                else ""
            )
            # last_history_user
            history = reporting.historicalreporting.all()
            try:
                last_history_user = history[0].history_user.get_full_name()
            except Exception:
                last_history_user = ""

            # dates
            created_at = (
                utc_to_local(reporting.created_at).strftime("%Y-%m-%dT%H:%M")
                if reporting.created_at
                else ""
            )
            found_at = (
                utc_to_local(reporting.found_at).strftime("%Y-%m-%dT%H:%M")
                if reporting.found_at
                else ""
            )
            updated_at = (
                utc_to_local(reporting.updated_at).strftime("%Y-%m-%dT%H:%M")
                if reporting.updated_at
                else ""
            )
            executed_at = (
                utc_to_local(reporting.executed_at).strftime("%Y-%m-%dT%H:%M")
                if reporting.executed_at
                else ""
            )
            due_at = (
                utc_to_local(reporting.due_at).strftime("%Y-%m-%dT%H:%M")
                if reporting.due_at
                else ""
            )

            # point
            if reporting.point:
                longitude = reporting.point.coords[0]
                latitude = reporting.point.coords[1]
            else:
                longitude = ""
                latitude = ""

            # direction
            possible_path = "reporting__fields__direction__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            dir_names = [
                item["name"] for item in options if item["value"] == reporting.direction
            ]
            direction = dir_names[0] if dir_names else ""

            # lane
            possible_path = "reporting__fields__lane__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            lane_names = [
                item["name"] for item in options if item["value"] == reporting.lane
            ]
            lane = lane_names[0] if lane_names else ""

            # track
            possible_path = "reporting__fields__track__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            track_names = [
                item["name"] for item in options if item["value"] == reporting.track
            ]
            track = track_names[0] if track_names else ""

            # branch
            possible_path = "reporting__fields__branch__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            branch_names = [
                item["name"] for item in options if item["value"] == reporting.branch
            ]
            branch = branch_names[0] if branch_names else ""

            # km reference
            km_reference = reporting.km_reference or ""

            # occurrence_kind
            possible_path = "reporting__fields__occurrencekind__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            occurrence_kind_names = [
                item["name"]
                for item in options
                if reporting.occurrence_type
                and item["value"] == reporting.occurrence_type.occurrence_kind
            ]
            occurrence_kind = occurrence_kind_names[0] if occurrence_kind_names else ""

            # form_data basics

            # Handle exceptions when trying to convert numbers to float
            # We may have problems if for some reason length is ".", for example
            try:
                length = float(reporting.form_data.get("length", 0) or 0)
            except Exception:
                length = 0
            try:
                width = float(reporting.form_data.get("width", 0) or 0)
            except Exception:
                width = 0
            try:
                height = float(reporting.form_data.get("height", 0) or 0)
            except Exception:
                height = 0

            notes = reporting.form_data.get("notes", "")

            # extra_columns
            reporting_formatted = get_obj_serialized(reporting, is_reporting_bi=True)
            possible_path = "reportingspreadsheet__extracolumns"
            extra_columns = get_obj_from_path(
                self.company.custom_options, possible_path
            )
            new_val = {}
            id_inventory = (
                getattr(reporting.parent, "uuid", "") if reporting.parent else ""
            )

            if extra_columns:
                for item in extra_columns:
                    json_logic = None
                    key = item.get("key", False)
                    logic = item.get("logic", False)
                    is_date = item.get("isDate", False)
                    is_select = item.get("isSelect", False)
                    is_array = item.get("isArray", False)
                    if key and logic:
                        try:
                            json_logic = apply_json_logic(logic, reporting_formatted)
                        except Exception:
                            pass
                    if is_select:
                        json_logic = return_select_value(
                            key, reporting, self.reference_values
                        )
                    if is_array:
                        json_logic = return_array_values(
                            item, reporting, self.reference_values
                        )
                    if not json_logic:
                        try:
                            json_logic = reporting.form_data[to_snake_case(key)]
                        except Exception:
                            pass
                        if json_logic in EMPTY_VALUES:
                            json_logic = ""
                    if is_date and json_logic:
                        json_logic = format_date(json_logic)
                    if isinstance(json_logic, dict):
                        new_val.update(json_logic)
                    else:
                        new_val[key] = json_logic

            if "csp" in new_val:
                try:
                    csp_field = next(
                        a
                        for a in reporting.occurrence_type.form_fields["fields"]
                        if ("api_name" in a and a["api_name"] == "csp")
                        or ("apiName" in a and a["apiName"] == "csp")
                    )
                    new_val["csp"] = apply_json_logic(csp_field["logic"])
                except Exception:
                    pass
                except StopIteration:
                    pass

            if "contratualCode" in new_val:
                try:
                    contratual_code_field = next(
                        a
                        for a in reporting.occurrence_type.form_fields["fields"]
                        if ("api_name" in a and a["api_name"] == "contratualCode")
                        or ("apiName" in a and a["apiName"] == "contratualCode")
                    )
                    new_val["contratualCode"] = apply_json_logic(
                        contratual_code_field["logic"]
                    )
                except Exception:
                    pass
                except StopIteration:
                    pass

            price = 0
            if "price" in reporting_formatted:
                price = reporting_formatted["price"]

            row = {
                "uuid": uuid,
                "link": url,
                "number": number,
                "roadName": road_name,
            }
            if self.include_city:
                row["cityCalc"] = reporting.city or ""
            row.update(
                {
                    "km": km,
                    "endKm": end_km,
                    "latitude": latitude,
                    "longitude": longitude,
                    "occurrenceType": occ_type,
                    "length": length,
                    "width": width,
                    "height": height,
                    "lane": lane,
                    "track": track,
                    "branch": branch,
                    "kmReference": km_reference,
                    "direction": direction,
                    "occurrenceKind": occurrence_kind,
                    "status": status,
                    "createdBy": created_by,
                    "updatedBy": last_history_user,
                    "firm": firm,
                    "subcompany": subcompany,
                    "job": job,
                    "createdAt": created_at,
                    "foundAt": found_at,
                    "updatedAt": updated_at,
                    "executedAt": executed_at,
                    "notes": notes,
                    "dueAt": due_at,
                    "price": price,
                    "construction": construction,
                    "idInventory": id_inventory,
                    **new_val,
                }
            )
            data.append(row)

        return data


class SpreadsheetResourceEndpoint:
    def __init__(self, queryset):
        self.queryset = queryset

    def get_data(self):
        data = []
        for p_resource in self.queryset:
            data_dict = {
                "reporting_uuid": str(p_resource.reporting.uuid),
                "reporting_number": p_resource.reporting.number,
                "resource_name": p_resource.resource.name,
                "amount": p_resource.amount,
                "unit_price": p_resource.unit_price,
                "total_price": p_resource.total_price,
            }
            data.append(data_dict)

        return data


class MultipleDailyReportSpreadsheetBase:
    def __init__(self, queryset, company):
        self.queryset = queryset
        self.company = company

    def translate_base_fields(self, field_name, value):
        options = get_obj_from_path(
            self.company.custom_options,
            "dailyreport__fields__{}__selectoptions__options".format(field_name),
        )
        if options and value:
            options_translated = {a["value"]: a["name"] for a in options}
            value_translated = options_translated.get(value, "")
            return value_translated
        return ""

    def get_rel_model_fields(
        self,
        queryset,
        model_suffix,
        rel_model_fields,
        prefetch_related_fields=[],
        select_options_fields=[],
        flat=False,
    ):
        active_filter = {"{}_relations__active".format(model_suffix): True}
        values = list(
            queryset.filter(**active_filter)
            .prefetch_related(*prefetch_related_fields)
            .values_list(flat=flat, *rel_model_fields)
        )
        if select_options_fields and values:
            for option_field in select_options_fields:
                options_model_suffix = to_flatten_str(model_suffix)
                options_field_suffix = to_flatten_str(option_field)
                options = get_obj_from_path(
                    self.company.custom_options,
                    "dailyreport{}__fields__{}__selectoptions__options".format(
                        options_model_suffix, options_field_suffix
                    ),
                )

                if options:
                    # Get the position of that field and substitute the reference value with
                    # the actual value if any options are found
                    field_position = rel_model_fields.index(option_field)
                    options_lookup = {
                        option["value"]: option["name"] for option in options
                    }

                    for i, value in enumerate(values):
                        try:
                            value_list = list(value)
                            value_list[field_position] = options_lookup[
                                value_list[field_position]
                            ]
                            values[i] = tuple(value_list)
                        except Exception:
                            pass

        return values


class MultipleDailyReportSpreadsheetEndpoint(MultipleDailyReportSpreadsheetBase):
    def get_km_intervals_formatted(self, mdr):
        road_intervals = ""
        km_intervals = ""
        km_intervals_list = sorted(
            get_km_intervals_field(mdr, only_query=False),
            key=lambda x: (x.get("roadName", ""), x.get("km", 0)),
        )
        left_paddings = [3]
        for km_interval in km_intervals_list:
            left_paddings.append(len(str(int(km_interval.get("km", 0)))))
            left_paddings.append(len(str(int(km_interval.get("end_km", 0)))))
        left_padding = max(left_paddings)
        for km_interval in km_intervals_list:
            road_intervals += "{}{}".format(
                "; " if road_intervals else "", km_interval.get("roadName", "")
            )
            km_intervals += "{}{} - {}".format(
                "; " if km_intervals else "",
                format_km(km_interval.get("km", 0), left_padding),
                format_km(km_interval.get("end_km", 0), left_padding),
            )
        return road_intervals, km_intervals

    def get_price_and_reporting_count(self, mdr):
        price = 0.0
        counter = 0
        if mdr.reportings.count() > 0:
            reportings = mdr.reportings.all()
            counter = len(reportings)
            for reporting in reportings:
                for item in reporting.reporting_resources.all():
                    price += item.total_price
        return price, counter

    def get_data(self):
        data = []
        signaling_filtered = DailyReportSignaling.objects.filter(
            multiple_daily_reports__in=self.queryset
        ).distinct()
        signaling_data_list = self.get_rel_model_fields(
            signaling_filtered,
            model_suffix="signaling",
            rel_model_fields=["multiple_daily_reports__uuid", "kind"],
            prefetch_related_fields=["multiple_daily_reports"],
            select_options_fields=["kind"],
        )
        for mdr in self.queryset:
            # basics
            uuid = str(mdr.uuid)
            roads, kms = self.get_km_intervals_formatted(mdr)
            morning_weather = translate_weather(mdr.morning_weather) or ""
            afternoon_weather = translate_weather(mdr.afternoon_weather) or ""
            night_weather = translate_weather(mdr.night_weather) or ""
            morning_conditions = translate_condition(mdr.morning_conditions) or ""
            afternoon_conditions = translate_condition(mdr.afternoon_conditions) or ""
            night_conditions = translate_condition(mdr.night_conditions) or ""
            use_reporting_resources = "Sim" if mdr.use_reporting_resources else "Não"
            day_without_work = "Sim" if mdr.day_without_work else "Não"
            compensation = "Sim" if mdr.compensation else "Não"
            number = mdr.number or ""

            # relationships
            created_by = mdr.created_by.get_full_name() if mdr.created_by else ""
            responsible = mdr.responsible.get_full_name() if mdr.responsible else ""
            inspector = mdr.inspector.get_full_name() if mdr.inspector else ""
            subcompany = (
                getattr(mdr.firm.subcompany, "name", "")
                if mdr.firm and mdr.firm.subcompany
                else ""
            )
            firm = getattr(mdr.firm, "name", "") if mdr.firm else ""
            approval_step = (
                getattr(mdr.approval_step, "name", "") if mdr.approval_step else ""
            )
            price, reporting_count = self.get_price_and_reporting_count(mdr)
            signaling_data = "; ".join(
                [
                    kind
                    for (mdr_uuid, kind) in signaling_data_list
                    if uuid == str(mdr_uuid) and kind is not None
                ]
            )

            # dates
            date = mdr.date.strftime("%d-%m-%Y") if mdr.date else ""
            created_at = (
                utc_to_local(mdr.created_at).strftime("%Y-%m-%dT%H:%M")
                if mdr.created_at
                else ""
            )

            data.append(
                {
                    "mdrUuid": uuid,
                    "roads": roads,
                    "kms": kms,
                    "morningWeather": morning_weather,
                    "afternoonWeather": afternoon_weather,
                    "nightWeather": night_weather,
                    "morningConditions": morning_conditions,
                    "afternoonConditions": afternoon_conditions,
                    "nightConditions": night_conditions,
                    "useReportingResources": use_reporting_resources,
                    "createdBy": created_by,
                    "responsible": responsible,
                    "inspector": inspector,
                    "subcompany": subcompany,
                    "firm": firm,
                    "approvalStep": approval_step,
                    "price": price,
                    "reportingCount": reporting_count,
                    "date": date,
                    "signalingData": signaling_data,
                    "dayWithoutWork": day_without_work,
                    "compensation": compensation,
                    "number": number,
                    "createdAt": created_at,
                }
            )
        return data


class DailyReportVehicleSpreadsheetEndpoint(MultipleDailyReportSpreadsheetBase):
    def get_data(self):
        data = []
        self.queryset = DailyReportVehicle.objects.filter(
            pk__in=[item.uuid for item in self.queryset]
        )

        vehicle_data = self.get_rel_model_fields(
            self.queryset,
            model_suffix="vehicle",
            rel_model_fields=[
                "multiple_daily_reports__uuid",
                "kind",
                "description",
                "contract_item_administration",
                "contract_item_administration__resource__resource__name",
                "contract_item_administration__contract_item_administration_services__description",
                "amount",
            ],
            prefetch_related_fields=[
                "multiple_daily_reports",
                "contract_item_administration",
                "contract_item_administration__resource",
                "contract_item_administration__resource__resource",
                "contract_item_administration__contract_item_administration_services",
            ],
            select_options_fields=["description"],
        )
        for (
            mdr_uuid,
            kind,
            description,
            contract_item_administration,
            resource_name,
            service_description,
            amount,
        ) in vehicle_data:
            kind_translated = self.translate_base_fields("kind", kind)
            data.append(
                {
                    "mdrUuid": mdr_uuid,
                    "kind": kind_translated if not contract_item_administration else "",
                    "description": description
                    if not contract_item_administration
                    else "{} ({})".format(resource_name, service_description),
                    "amount": amount,
                }
            )

        return data


class DailyReportEquipmentSpreadsheetEndpoint(MultipleDailyReportSpreadsheetBase):
    def get_data(self):
        data = []
        self.queryset = DailyReportEquipment.objects.filter(
            pk__in=[item.uuid for item in self.queryset]
        )
        equipment_data = self.get_rel_model_fields(
            self.queryset,
            model_suffix="equipment",
            rel_model_fields=[
                "multiple_daily_reports__uuid",
                "kind",
                "description",
                "contract_item_administration",
                "contract_item_administration__resource__resource__name",
                "contract_item_administration__contract_item_administration_services__description",
                "amount",
            ],
            prefetch_related_fields=[
                "multiple_daily_reports",
                "contract_item_administration",
                "contract_item_administration__resource",
                "contract_item_administration__resource__resource",
                "contract_item_administration__contract_item_administration_services",
                "amount",
            ],
            select_options_fields=["description"],
        )
        for (
            mdr_uuid,
            kind,
            description,
            contract_item_administration,
            resource_name,
            service_description,
            amount,
        ) in equipment_data:
            kind_translated = self.translate_base_fields("kind", kind)
            data.append(
                {
                    "mdrUuid": mdr_uuid,
                    "kind": kind_translated if not contract_item_administration else "",
                    "description": description
                    if not contract_item_administration
                    else "{} ({})".format(resource_name, service_description),
                    "amount": amount,
                }
            )
        return data


class DailyReportWorkerSpreadsheetEndpoint(MultipleDailyReportSpreadsheetBase):
    def get_data(self):
        data = []
        self.queryset = DailyReportWorker.objects.filter(
            pk__in=[item.uuid for item in self.queryset]
        )
        worker_data = self.get_rel_model_fields(
            self.queryset,
            model_suffix="worker",
            rel_model_fields=[
                "multiple_daily_reports__uuid",
                "role",
                "contract_item_administration",
                "contract_item_administration__resource__resource__name",
                "contract_item_administration__contract_item_administration_services__description",
                "amount",
            ],
            prefetch_related_fields=[
                "role",
                "contract_item_administration",
                "contract_item_administration__resource__resource"
                "contract_item_administration__resource__resource",
                "contract_item_administration__contract_item_administration_services",
            ],
            select_options_fields=["role"],
        )
        for (
            mdr_uuid,
            role,
            contract_item_administration,
            resource_name,
            service_description,
            amount,
        ) in worker_data:
            data.append(
                {
                    "mdrUuid": mdr_uuid,
                    "role": role
                    if not contract_item_administration
                    else "{} ({})".format(resource_name, service_description),
                    "amount": amount,
                }
            )
        return data


class DailyReportOccurrenceSpreadsheetEndpoint(MultipleDailyReportSpreadsheetBase):
    def get_data(self):
        data = []
        self.queryset = DailyReportOccurrence.objects.filter(
            pk__in=[item.uuid for item in self.queryset]
        )

        occurrence_option_custom_options = get_obj_from_path(
            self.company.custom_options,
            "daily_report_occurrence__fields__origin__select_options__options",
        )
        occurrence_option = (
            occurrence_option_custom_options
            if occurrence_option_custom_options
            else TRANSLATE_OCCURRENCE_ORIGIN_CHOICES
        )
        occurrence_option = {a["value"]: a["name"] for a in occurrence_option}
        occurrence_data = self.get_rel_model_fields(
            self.queryset,
            model_suffix="occurrence",
            rel_model_fields=[
                "multiple_daily_reports__uuid",
                "origin",
                "description",
                "starts_at",
                "ends_at",
                "extra_info",
                "impact_duration",
            ],
            prefetch_related_fields=["multiple_daily_reports"],
            select_options_fields=["description"],
        )

        for (
            mdr_uuid,
            origin,
            description,
            starts_at,
            ends_at,
            extra_info,
            impact_duration,
        ) in occurrence_data:
            data.append(
                {
                    "mdrUuid": mdr_uuid,
                    "origin": occurrence_option.get(origin, ""),
                    "description": description,
                    "startsAt": starts_at.strftime("%H:%M") if starts_at else "",
                    "endsAt": ends_at.strftime("%H:%M") if ends_at else "",
                    "extraInfo": extra_info,
                    "impactDuration": impact_duration or "",
                }
            )
        return data


class DailyReportResourceSpreadsheetEndpoint(MultipleDailyReportSpreadsheetBase):
    def get_data(self):
        data = []
        self.queryset = DailyReportResource.objects.filter(
            pk__in=[item.uuid for item in self.queryset]
        )

        resource_data = self.get_rel_model_fields(
            self.queryset,
            model_suffix="resource",
            rel_model_fields=[
                "multiple_daily_reports__uuid",
                "kind",
                "resource__name",
                "resource__resource_service_orders__contract",
                "resource__resource_service_orders__resource_contract_unit_price_items__contract_item_unit_price_services__description",
                "resource__resource_service_orders__resource_contract_administration_items__contract_item_administration_services__description",
                "amount",
                "resource__unit",
            ],
            prefetch_related_fields=[
                "multiple_daily_reports",
                "resource",
                "resource__resource_service_orders",
                "resource__resource_service_orders__contract",
                "resource__resource_service_orders__resource_contract_unit_price_items",
                "resource__resource_service_orders__resource_contract_unit_price_items__contract_item_unit_price_services",
                "resource__resource_service_orders__resource_contract_administration_items",
                "resource__resource_service_orders__resource_contract_administration_items__contract_item_administration_services",
            ],
        )
        for (
            mdr_uuid,
            kind,
            resource_name,
            contract,
            service_unit_description,
            service_adm_description,
            amount,
            resource_unit,
        ) in resource_data:
            kind_translated = self.translate_base_fields("kind", kind)
            data.append(
                {
                    "mdrUuid": mdr_uuid,
                    "kind": kind_translated,
                    "name": resource_name
                    if not contract
                    else "{} ({})".format(
                        resource_name,
                        service_unit_description
                        if service_unit_description
                        else service_adm_description
                        if service_adm_description
                        else "",
                    ),
                    "amount": amount,
                    "unit": resource_unit or "",
                }
            )
        return data


class DailyReportReportingResourceSpreadsheetEndpoint(
    MultipleDailyReportSpreadsheetBase
):
    def get_data(self):
        data = []
        for item in self.queryset:

            data.append(
                {
                    "uuid": str(item.reporting.uuid) if item.reporting else "",
                    "resourceId": str(item.uuid),
                    "name": item.resource.name if item.resource else "",
                    "amount": item.amount,
                    "unit": item.resource.unit if item.resource else "",
                }
            )

        return data


class DailyReportReportingSpreadsheetEndpoint(MultipleDailyReportSpreadsheetBase):
    def get_data(self):
        if self.queryset:
            data = SpreadsheetEndpoint(
                queryset=self.queryset, company=self.company
            ).get_data()
            return data


class DailyReportReportingRelationshipSpreadsheetEndpoint(
    MultipleDailyReportSpreadsheetBase
):
    def get_data(self):
        data = []
        for item in self.queryset:
            data.append(
                {
                    "mdrUuid": str(item.multipledailyreport_id),
                    "uuid": str(item.reporting_id),
                }
            )

        return data


class InventorySpreadsheeetEndpoint:
    def __init__(self, queryset, company):
        self.queryset = queryset
        self.company = company
        self.reference_values = {
            str(a.uuid): a.name
            for a in OccurrenceType.objects.filter(company=self.company)
        }

    def get_data(self):
        data = []
        for inventory in self.queryset:
            # basics
            uuid = str(inventory.uuid)
            number = inventory.number or ""
            road_name = inventory.road_name or ""
            km = inventory.km
            end_km = inventory.end_km or km

            url = "{}/#/SharedLink/Inventory/{}/show?company={}".format(
                settings.FRONTEND_URL, str(inventory.uuid), str(self.company.uuid)
            )
            company_name = self.company.name or ""

            # relationships
            active_inspection_uuid = (
                getattr(inventory.active_inspection, "uuid", "")
                if inventory.active_inspection
                else ""
            )
            created_by = (
                inventory.created_by.get_full_name() if inventory.created_by else ""
            )
            occ_type = (
                getattr(inventory.occurrence_type, "name", "")
                if inventory.occurrence_type
                else ""
            )

            # dates
            created_at = (
                utc_to_local(inventory.created_at).strftime("%Y-%m-%dT%H:%M")
                if inventory.created_at
                else ""
            )
            found_at = (
                utc_to_local(inventory.found_at).strftime("%Y-%m-%dT%H:%M")
                if inventory.found_at
                else ""
            )
            updated_at = (
                utc_to_local(inventory.updated_at).strftime("%Y-%m-%dT%H:%M")
                if inventory.updated_at
                else ""
            )

            # point
            if inventory.point:
                longitude = inventory.point.coords[0]
                latitude = inventory.point.coords[1]
            else:
                longitude = ""
                latitude = ""

            # project_km and km_reference
            project_km = inventory.project_km or ""
            project_end_km = inventory.project_end_km or ""
            km_reference = inventory.km_reference or ""

            # direction
            possible_path = "reporting__fields__direction__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            dir_names = [
                item["name"] for item in options if item["value"] == inventory.direction
            ]
            direction = dir_names[0] if dir_names else ""

            # branch
            possible_path = "reporting__fields__branch__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            branch_names = [
                item["name"] for item in options if item["value"] == inventory.branch
            ]
            branch = branch_names[0] if branch_names else ""

            # lane
            possible_path = "reporting__fields__lane__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            lane_names = [
                item["name"] for item in options if item["value"] == inventory.lane
            ]
            lane = lane_names[0] if lane_names else ""

            # track
            possible_path = "reporting__fields__track__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            track_names = [
                item["name"] for item in options if item["value"] == inventory.track
            ]
            track = track_names[0] if track_names else ""

            # lot
            possible_path = "reporting__fields__lot__selectoptions__options"
            options = get_obj_from_path(self.company.custom_options, possible_path)
            lot_names = [
                item["name"] for item in options if item["value"] == inventory.lot
            ]
            lot = lot_names[0] if lot_names else ""

            # form_data
            notes = inventory.form_data.get("notes", "")

            # Handle exceptions when trying to convert numbers to float
            # We may have problems if for some reason length is ".", for example
            try:
                length = float(inventory.form_data.get("length", 0) or 0)
            except Exception:
                length = 0
            try:
                width = float(inventory.form_data.get("width", 0) or 0)
            except Exception:
                width = 0
            try:
                height = float(inventory.form_data.get("height", 0) or 0)
            except Exception:
                height = 0

            # extra_columns
            inventory_formatted = get_obj_serialized(inventory, is_inventory_bi=True)
            possible_path = "inventoryspreadsheet__extracolumns"
            extra_columns = get_obj_from_path(
                self.company.custom_options, possible_path
            )
            new_val = {}

            if extra_columns:
                for item in extra_columns:
                    json_logic = None
                    key = item.get("key", False)
                    logic = item.get("logic", False)
                    is_date = item.get("isDate", False)
                    is_select = item.get("isSelect", False)
                    is_array = item.get("isArray", False)
                    if key and logic:
                        try:
                            json_logic = apply_json_logic(logic, inventory_formatted)
                        except Exception:
                            pass
                    if is_select:
                        json_logic = return_select_value(
                            key, inventory, self.reference_values
                        )
                    if is_array:
                        json_logic = return_array_values(
                            item, inventory, self.reference_values
                        )
                    if not json_logic:
                        try:
                            json_logic = inventory.form_data[to_snake_case(key)]
                        except Exception:
                            pass
                        if json_logic in EMPTY_VALUES:
                            json_logic = ""
                    if is_date and json_logic:
                        json_logic = format_date(json_logic)
                    if isinstance(json_logic, dict):
                        new_val.update(json_logic)
                    else:
                        new_val[key] = json_logic

            data.append(
                {
                    "uuid": uuid,
                    "link": url,
                    "number": number,
                    "companyName": company_name,
                    "activeInspectionId": active_inspection_uuid,
                    "roadName": road_name,
                    "km": km,
                    "endKm": end_km,
                    "projectKm": project_km,
                    "projectEndKm": project_end_km,
                    "kmReference": km_reference,
                    "latitude": latitude,
                    "longitude": longitude,
                    "occurrenceType": occ_type,
                    "lane": lane,
                    "track": track,
                    "branch": branch,
                    "lot": lot,
                    "direction": direction,
                    "createdBy": created_by,
                    "createdAt": created_at,
                    "foundAt": found_at,
                    "updatedAt": updated_at,
                    "notes": notes,
                    "length": length,
                    "width": width,
                    "height": height,
                    **new_val,
                }
            )

        return data
