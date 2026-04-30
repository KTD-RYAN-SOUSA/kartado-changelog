from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from apps.reportings.models import Reporting, ReportingFile
from helpers.apps.ccr_report_utils.form_data import new_get_form_data
from helpers.strings import format_km, get_obj_from_path, to_snake_case


def get_km(reporting: Reporting, default: str = None) -> str:
    formatted_km = default
    try:
        formatted_km = format_km(reporting, "km", 3)
    except Exception:
        pass
    return formatted_km


def get_end_km(reporting: Reporting, default: str = "") -> str:
    formatted_km = default
    try:
        formatted_km = format_km(reporting, "end_km", 3)
    except Exception:
        pass
    return formatted_km


def get_custom_option_value(
    reporting: Reporting, field_name: str, value: str = None
) -> str:
    try:
        possible_path = "reporting__fields__{}__selectoptions__options".format(
            field_name
        )
        options = get_obj_from_path(reporting.company.custom_options, possible_path)

        name = next(a["name"] for a in options if a["value"] == value)
        return name
    except Exception:
        return None


def get_custom_option(
    reporting: Reporting, field_name: str, default: str = None
) -> str:
    try:
        value = getattr(reporting, field_name)
        possible_path = "reporting__fields__{}__selectoptions__options".format(
            field_name
        )
        options = get_obj_from_path(reporting.company.custom_options, possible_path)

        name = next(a["name"] for a in options if a["value"] == value)
        return name
    except Exception:
        return default


def get_previous_found_at_reporting(report: Reporting, *fields) -> Reporting:
    previous_reporting = None
    if report.found_at is not None:
        try:
            previous_reporting = (
                Reporting.objects.filter(
                    parent__uuid=report.parent.uuid,
                    occurrence_type=report.occurrence_type,
                    found_at__lt=report.found_at,
                )
                .only(*fields)
                .latest("found_at")
            )
        except Exception:
            pass
    return previous_reporting


def get_previous_campaign_report(
    occurrence_type: str, report: Reporting, *fields
) -> Reporting:
    try:
        previous_year = report.form_data["inspection_campaign_year"] - 1
        previous_reporting = (
            Reporting.objects.filter(
                parent__uuid=report.parent.uuid,
                occurrence_type=occurrence_type,
                form_data__inspection_campaign_year=previous_year,
            )
            .only(*fields)
            .latest("created_at")
        )
        return previous_reporting
    except Exception:
        return None


def get_previous_year_report(report: Reporting, years: int, *fields) -> Reporting:
    previous_reporting = None
    try:
        found_at = get_found_at(report)

        previous_year = found_at.year - years
        previous_reporting = (
            Reporting.objects.filter(
                parent__uuid=report.parent.uuid,
                occurrence_type__uuid=report.occurrence_type.uuid,
                found_at__year=previous_year,
            )
            .only(*fields)
            .latest("found_at")
        )
    except Exception as e:
        print(e)

    return previous_reporting


def get_parent_serial(reporting: Reporting) -> str:
    try:
        return reporting.parent.number
    except Exception:
        return ""


def get_status_name(reporting: Reporting) -> str:
    if reporting.status is not None:
        return reporting.status.name
    else:
        return ""


def get_occurrence_type_name(reporting: Reporting) -> str:
    if reporting.occurrence_type is not None:
        return reporting.occurrence_type.name
    else:
        return ""


def get_serial(reporting: Reporting) -> str:
    if reporting.number is not None:
        return reporting.number
    else:
        return ""


def get_direction(reporting: Reporting, default: str = "") -> str:
    direction = default
    try:
        direction = get_custom_option(reporting, "direction")
    except Exception:
        pass
    return direction


def get_lane(reporting: Reporting) -> str:
    try:
        return get_custom_option(reporting, "lane")
    except Exception:
        return ""


def get_identification(reporting: Reporting, default=None) -> str:
    try:
        return str(new_get_form_data(reporting, "idCcrAntt", default=default))
    except Exception:
        return default


def get_road_name(reporting: Reporting) -> str:
    if reporting.road_name is not None:
        return reporting.road_name
    else:
        return ""


def get_reporting_files(
    reporting: Reporting, only_shared: bool, *fields
) -> List[ReportingFile]:
    try:
        query_set = ReportingFile.objects.filter(reporting__uuid=reporting.uuid)
        if only_shared:
            query_set.filter(is_shared=True)
        query_set.only(*fields)
        return [linked for linked in query_set]
    except Exception:
        return []


def get_brasilia_date(date: datetime) -> datetime:
    time_delta = timedelta(hours=-3)
    time_zone = timezone(time_delta)
    return date.astimezone(time_zone)


def get_found_at(reporting: Reporting) -> datetime:
    if reporting.found_at is not None:
        return get_brasilia_date(reporting.found_at)
    else:
        return None


class FormDataImageArray:
    def __init__(
        self,
        display_name: str,
        sectionSubtitle: str,
        nesting_api_names: Tuple[str],
        uuids: List[str],
    ):
        self.display_name = display_name
        self.sectionSubtitle = sectionSubtitle
        self.nesting_api_names = nesting_api_names
        self.uuids = uuids


def form_data_images_step(
    fields: dict,
    form_data: dict,
    key: Tuple[str],
    image_groups: Dict[str, FormDataImageArray],
) -> None:
    """
    Recursive step of deep_image_search.
    """
    for field in fields:
        api_name = field["apiName"]
        form_data_key = to_snake_case(api_name)
        key = key + (api_name,)
        if field["dataType"] == "innerImagesArray":
            image_uuids: List = form_data.get(form_data_key, [])
            if isinstance(image_uuids, list) and len(image_uuids) > 0:
                d_underscore_key = "__".join(key)
                if d_underscore_key not in image_groups:
                    image_array = FormDataImageArray(
                        field.get("displayName", None),
                        field.get("sectionSubtitle", None),
                        key,
                        image_uuids,
                    )
                    image_groups[d_underscore_key] = image_array
                else:
                    image_array = image_groups[d_underscore_key]
                    image_array.uuids += image_uuids
        elif field["dataType"] == "arrayOfObjects":
            inner_fields = field["innerFields"]
            if form_data_key in form_data:
                for obj in form_data[form_data_key]:
                    form_data_images_step(inner_fields, obj, key, image_groups)

        key = key[:-1]


def form_data_images_grouped(reporting: Reporting) -> Dict[str, FormDataImageArray]:
    """
    DFS to get every image array in form data.
    Returns dictionary mapping by a
    double underscore notation access key to the field
    to lists of ReportingFile UUIDs.
    """
    fields = reporting.occurrence_type.form_fields.get("fields", [])
    form_data = reporting.form_data
    image_groups: Dict[str, FormDataImageArray] = {}
    form_data_images_step(fields, form_data, tuple(), image_groups)
    return image_groups


def form_data_images(reporting: Reporting) -> List[ReportingFile]:
    """
    Returns a list of uuids that in the form data of the reporting.
    """
    image_groups = form_data_images_grouped(reporting)
    uuids = []
    for group in image_groups.values():
        uuids.extend(group.uuids)
    return uuids
