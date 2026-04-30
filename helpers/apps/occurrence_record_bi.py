from django.conf import settings

from apps.service_orders.models import ServiceOrderActionStatus
from helpers.apps.json_logic import apply_json_logic
from helpers.dates import format_date
from helpers.input_masks import (
    format_cpf_brazilin,
    format_mobile_number_brazilin,
    format_phone_number_brazilin,
)
from helpers.serializers import get_obj_serialized
from helpers.strings import UF_CODE, get_obj_from_path


class OccurrenceRecordBIEndpoint:
    # Gets the raw data and prepares it to return an array of OccurrenceRecords
    # in the `OccurrenceRecord/BI` enpoint.
    # The ways the fields are sorted are according to the Model.

    def __init__(self, queryset):
        self.queryset = queryset

    def get_data(self):
        data = []

        if self.queryset:
            # Prepare statuses before extracting data
            statuses = ServiceOrderActionStatus.objects.filter(
                companies=self.queryset[0].company
            ).distinct()

            # Prepare relevant history
            records_uuids = [record.uuid for record in self.queryset]
            HistoricalOccurrenceRecord = self.queryset[
                0
            ].historicaloccurrencerecord.model
            record_histories_values = (
                HistoricalOccurrenceRecord.objects.filter(uuid__in=records_uuids)
                .values_list(
                    "uuid",
                    "status",
                    "history_date",
                    "history_user__first_name",
                    "history_user__last_name",
                )
                .order_by("history_date")
            )

            # Extract data
            for record in self.queryset:
                # Check if record is Operational
                is_operational_record = record.operational_control is not None

                # basic information
                url = "{}/#/SharedLink/{}/{}/show?company={}".format(
                    settings.FRONTEND_URL,
                    "OccurrenceRecord",
                    str(record.uuid),
                    str(record.company.uuid),
                )
                datetime = (
                    record.datetime.strftime("%Y-%m-%dT%H:%M")
                    if record.datetime
                    else ""
                )
                number = record.number or ""
                company = getattr(record.company, "name", "") if record.company else ""
                created_at = (
                    record.created_at.strftime("%Y-%m-%dT%H:%M")
                    if record.created_at
                    else ""
                )
                updated_at = (
                    record.updated_at.strftime("%Y-%m-%dT%H:%M")
                    if record.updated_at
                    else ""
                )

                # location
                uf_code = UF_CODE.get(str(record.uf_code), "")
                city = getattr(record.city, "name", "") if record.city else ""
                location = (
                    getattr(record.location, "name", "") if record.location else ""
                )

                # place_on_dam
                possible_path = (
                    "occurrencerecord__fields__placeondam__selectoptions__options"
                )
                options = get_obj_from_path(
                    record.company.custom_options, possible_path
                )
                place_on_dam_names = [
                    item["name"]
                    for item in options
                    if item["value"] == record.place_on_dam
                ]
                place_on_dam = place_on_dam_names[0] if place_on_dam_names else ""

                river = getattr(record.river, "name", "") if record.river else ""

                # point
                if record.point:
                    longitude = record.point.coords[0]
                    latitude = record.point.coords[1]
                else:
                    longitude = ""
                    latitude = ""

                distance_from_dam = record.distance_from_dam or ""
                other_reference = record.other_reference or ""

                # created_by
                created_by = (
                    record.created_by.get_full_name() if record.created_by else ""
                )

                # occurrence_kind
                possible_path = (
                    "occurrencerecord__fields__occurrencekind__selectoptions__options"
                )
                options = get_obj_from_path(
                    record.company.custom_options, possible_path
                )
                occurrence_kind_names = (
                    [
                        item["name"]
                        for item in options
                        if item["value"] == record.occurrence_type.occurrence_kind
                    ]
                    if record.occurrence_type
                    else []
                )
                occurrence_kind = (
                    occurrence_kind_names[0] if occurrence_kind_names else ""
                )

                # occurrence_type
                occ_type = (
                    getattr(record.occurrence_type, "name", "")
                    if record.occurrence_type
                    else ""
                )

                # relationships
                status = getattr(record.status, "name", "") if record.status else ""
                service_order = (
                    ", ".join([item.number for item in record.service_orders.all()])
                    if record.service_orders.exists()
                    else ""
                )
                firm = getattr(record.firm, "name", "") if record.firm else ""
                responsible = (
                    record.responsible.get_full_name() if record.responsible else ""
                )

                # extra_columns
                record_formatted = get_obj_serialized(record, is_occurrence_record=True)
                possible_path = "occurrencerecord__exporter__extracolumns"
                extra_columns = get_obj_from_path(
                    record.company.custom_options, possible_path
                )
                new_val = {}
                if extra_columns:
                    for item in extra_columns:
                        json_logic = None
                        key = item.get("key", False)
                        logic = item.get("logic", False)
                        is_date = item.get("isDate", False)
                        if key and logic:
                            try:
                                json_logic = apply_json_logic(logic, record_formatted)
                            except Exception:
                                pass
                        if not json_logic:
                            try:
                                json_logic = record.form_data[key]
                            except Exception:
                                pass
                        if is_date and json_logic:
                            json_logic = format_date(json_logic)
                        new_val[key] = json_logic

                # features
                feature_collection = record_formatted.get("featureCollection")
                feature_count = (
                    len(feature_collection.get("features", []))
                    if feature_collection
                    else 0
                )

                # properties
                property_intersections = get_obj_from_path(
                    record_formatted, "formdata__propertyintersections"
                )
                property_intersections_count = len(property_intersections)

                # additional_values
                if is_operational_record:
                    # contract
                    record_contract = record.operational_control.contract
                    contract = (
                        getattr(record_contract, "name", "") if record_contract else ""
                    )
                    additional_values = {"contract": contract}
                else:
                    # origin
                    possible_path = (
                        "occurrencerecord__fields__origin__selectoptions__options"
                    )
                    options = get_obj_from_path(
                        record.company.custom_options, possible_path
                    )
                    origin_names = [
                        item["name"]
                        for item in options
                        if item["value"] == record.origin
                    ]
                    origin = origin_names[0] if origin_names else ""

                    # origin_media
                    possible_path = (
                        "occurrencerecord__fields__originmedia__selectoptions__options"
                    )
                    options = get_obj_from_path(
                        record.company.custom_options, possible_path
                    )
                    origin_media_names = [
                        item["name"]
                        for item in options
                        if item["value"] == record.origin_media
                    ]
                    origin_media = origin_media_names[0] if origin_media_names else ""

                    # informer
                    informer_name = ""
                    informer_mail = ""
                    informer_mobile = ""
                    informer_phone = ""
                    informer_cpf = ""
                    informer_qualification = ""

                    if record.informer:
                        informer_name = record.informer.get("firstName", "")
                        informer_mail = record.informer.get("mail", "")
                        informer_mobile = record.informer.get("mobile", "")
                        informer_phone = record.informer.get("phone", "")
                        informer_cpf = record.informer.get("cpf", "")

                        if informer_mobile:
                            informer_mobile = format_mobile_number_brazilin(
                                informer_mobile
                            )

                        if informer_phone:
                            informer_phone = format_phone_number_brazilin(
                                informer_phone
                            )

                        if informer_mobile:
                            informer_mobile = format_mobile_number_brazilin(
                                informer_mobile
                            )

                        if informer_cpf:
                            informer_cpf = format_cpf_brazilin(informer_cpf)

                        informer_qualification = record.informer.get(
                            "qualification", ""
                        )

                    # reviews
                    reviews = record.reviews or 0

                    # parent_action
                    parent_action = (
                        getattr(record.parent_action, "name", "")
                        if record.parent_action
                        else ""
                    )

                    # handle statuses
                    statuses_dates_and_users = {}
                    for status_candidate in statuses:
                        status_name = status_candidate.name.replace(" ", "")
                        date_key = "status{}At".format(status_name)
                        user_key = "status{}By".format(status_name)

                        try:
                            status_hist = next(
                                (
                                    date,
                                    "{} {}".format(user_first_name, user_last_name),
                                )
                                for (
                                    record_uuid,
                                    status_uuid,
                                    date,
                                    user_first_name,
                                    user_last_name,
                                ) in record_histories_values
                                if record_uuid == record.uuid
                                and status_uuid == status_candidate.uuid
                            )
                        except Exception:
                            continue
                        else:
                            hist_date, hist_user_name = status_hist
                            statuses_dates_and_users[date_key] = hist_date.strftime(
                                "%Y-%m-%dT%H:%M"
                            )
                            statuses_dates_and_users[user_key] = hist_user_name

                    additional_values = {
                        "origin": origin,
                        "originMedia": origin_media,
                        "informerName": informer_name,
                        "informerMail": informer_mail,
                        "informerMobile": informer_mobile,
                        "informerPhone": informer_phone,
                        "informerCPF": informer_cpf,
                        "informerQualification": informer_qualification,
                        "reviews": reviews,
                        "parentAction": parent_action,
                        **statuses_dates_and_users,
                    }

                data.append(
                    {
                        "link": url,
                        "datetime": datetime,
                        "number": number,
                        "company": company,
                        "uf": uf_code,
                        "city": city,
                        "location": location,
                        "placeOnDam": place_on_dam,
                        "river": river,
                        "latitude": latitude,
                        "longitude": longitude,
                        "distanceFromDam": distance_from_dam,
                        "otherReference": other_reference,
                        "createdBy": created_by,
                        "occurrenceKind": occurrence_kind,
                        "occurrenceType": occ_type,
                        "createdAt": created_at,
                        "updatedAt": updated_at,
                        "status": status,
                        "serviceOrder": service_order,
                        "firm": firm,
                        "responsible": responsible,
                        "featureCollection": feature_collection,
                        "featureCount": feature_count,
                        "propertyIntersectionsCount": property_intersections_count,
                        **additional_values,
                        **new_val,
                    }
                )

        return data
