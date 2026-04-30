from collections import defaultdict

from helpers.strings import get_obj_from_path, to_snake_case


def get_topics(form_fields, form_data, names=True):
    fields = form_fields.get("fields", [])
    try:
        inspection_topics = next(
            a
            for a in fields
            if ("api_name" in a and a["api_name"] == "inspectionTopics")
            or ("apiName" in a and a["apiName"] == "inspectionTopics")
        )
        inspection_topics_obj = get_obj_from_path(
            inspection_topics, "selectoptions__options"
        )
    except Exception:
        inspection_topics_obj = {}

    form_data_inspection_topics = form_data.get("inspection_topics", [])
    inspection_topics_translation = {
        item["value"]: item["name"] for item in inspection_topics_obj
    }

    names_list = []
    topics = defaultdict(list)
    for key, value in inspection_topics_translation.items():
        if key in form_data_inspection_topics:
            try:
                name = value.split(" ")[-1]
                if names:
                    names_list.append(name)
                else:
                    topics[value.split(" ")[0]].append(name)
            except Exception:
                continue

    return names_list if names else dict(topics)


def get_form_fields(occurrence_type):
    try:
        return occurrence_type.form_fields["fields"]
    except Exception:
        return []


def form_fields_dict(occurrence_type):
    form_fields = {}
    fields = get_form_fields(occurrence_type)

    for field in fields:
        api_name = field.get("api_name", False) or field.get("apiName", False)
        data_type = field.get("data_type", False) or field.get("dataType", False)
        auto_fill = (
            field.get("autofill", False)
            or field.get("autoFill", False)
            or field.get("auto_fill", False)
        )
        form_fields[api_name] = {"data_type": data_type, "autofill": auto_fill}

    return form_fields


def get_form_metadata(
    form_data: dict, occurrence_type, form_metadata: dict = {}, old_form_data: dict = {}
):
    fields = get_form_fields(occurrence_type)

    for field in fields:
        api_name = to_snake_case(field.get("api_name", "") or field.get("apiName", ""))
        data_type = field.get("data_type") or field.get("dataType")
        auto_fill = (
            field.get("autofill") or field.get("autoFill") or field.get("auto_fill")
        )

        if api_name:
            in_form_metadata = api_name in form_metadata
            in_form_data = (
                api_name in form_data if isinstance(form_data, dict) else False
            )

            if auto_fill is not None and data_type and data_type != "arrayOfObjects":
                if in_form_data and not in_form_metadata:
                    form_metadata[api_name] = {"manually_specified": True}
                elif not in_form_data:
                    form_metadata[api_name] = {"manually_specified": False}
            if auto_fill is None and in_form_metadata:
                del form_metadata[api_name]

    return form_metadata


def get_api_name(field):
    if "apiName" in field:
        return to_snake_case(field["apiName"])
    elif "api_name" in field:
        return to_snake_case(field["api_name"])
    else:
        return None


def clean_form_data(form_data, occurrence_type):
    ret_data = {}
    if "fields" in occurrence_type.form_fields:
        fields = [get_api_name(a) for a in occurrence_type.form_fields["fields"]]

        accepted = []
        discarded = []

        for field in form_data.keys():
            if field in fields:
                ret_data[field] = form_data[field]
                accepted.append(field)
            else:
                discarded.append(field)

    return ret_data


def merge_monitoring_and_therapy_data(
    monitoring_form_data, therapy_item, occurrence_type
):
    # Campos que não devem ser copiados da monitoração
    excluded_fields = ["therapy"]

    # Filtra dados da monitoração excluindo campos especiais
    monitoring_data = {
        k: v for k, v in monitoring_form_data.items() if k not in excluded_fields
    }

    merged_data = {**monitoring_data, **therapy_item}

    # Limpa campos inválidos baseado no form_fields do occurrence_type
    result = clean_form_data(merged_data, occurrence_type)

    return result
