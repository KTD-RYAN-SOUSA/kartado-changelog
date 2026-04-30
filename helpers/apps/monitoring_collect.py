import uuid

from apps.monitorings.models import MonitoringCollect
from helpers.strings import keys_to_snake_case


def create_monitoring_collect(obj_dict, record):
    snake_case_obj = keys_to_snake_case(obj_dict)
    valid_data = {}
    valid_data["uuid"] = str(uuid.uuid4())
    valid_data["company_id"] = record.company_id
    valid_data["datetime"] = snake_case_obj.get("datetime", None)
    valid_data["created_by_id"] = record.created_by_id
    valid_data["responsible_id"] = snake_case_obj.get("responsible", None)
    valid_data["parameter_group_id"] = snake_case_obj.get("parameter_group", None)
    valid_data["monitoring_frequency_id"] = snake_case_obj.get(
        "monitoring_frequency", None
    )
    valid_data["monitoring_point_id"] = snake_case_obj.get("monitoring_point", None)
    valid_data["occurrence_record_id"] = str(record.uuid)
    valid_data["dict_form_data"] = snake_case_obj.get("dict_form_data", {})
    valid_data["array_form_data"] = snake_case_obj.get("array_form_data", [])

    try:
        collect = MonitoringCollect.objects.create(**valid_data)
    except Exception as e:
        print(e)
    else:
        print(collect.uuid)
    return
