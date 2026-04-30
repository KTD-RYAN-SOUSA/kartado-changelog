import unicodedata
from datetime import datetime
from typing import List

from helpers.strings import (
    UF_CODE,
    get_obj_from_path,
    keys_to_snake_case,
    to_snake_case,
)


def normalize_text(text):
    """
    Normalize text by removing accents and converting to lowercase.
    This allows for efficient index usage without function calls in SQL.
    """
    if not text:
        return ""

    # Convert to string if not already
    text_str = str(text)

    # Remove accents using unicodedata
    normalized = unicodedata.normalize("NFD", text_str)
    ascii_text = "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    # Convert to lowercase
    return ascii_text.lower()


def get_complex_translation(field, values, keywords):
    if "select_options" in field:
        if "options" in field["select_options"]:
            for option in field["select_options"]["options"]:
                if "value" in option and "name" in option:
                    if isinstance(values, list):
                        for value in values:
                            if (
                                option["value"] == value
                                and normalize_text(option["name"]) not in keywords
                            ):
                                keywords.append(normalize_text(option["name"]))
                    else:
                        if (
                            option["value"] == values
                            and normalize_text(option["name"]) not in keywords
                        ):
                            keywords.append(normalize_text(option["name"]))
    return keywords


def get_translation(form_data, fields, keywords):
    need_translation = ["select", "array_of_objects", "select_multiple", "uf"]

    for field in fields:
        snake_field = keys_to_snake_case(field)
        if "api_name" in snake_field and "data_type" in snake_field:
            api_name = to_snake_case(snake_field["api_name"])
            data_type = to_snake_case(snake_field["data_type"]).lower()
            if api_name in form_data:
                if data_type in ["boolean", "timestamp"] or isinstance(
                    form_data[api_name], bool
                ):
                    continue

                if (
                    data_type not in need_translation
                    and normalize_text(form_data[api_name]) not in keywords
                ):
                    keywords.append(normalize_text(form_data[api_name]))

                elif data_type == "uf":
                    if (
                        str(form_data[api_name]) in UF_CODE
                        and normalize_text(UF_CODE[str(form_data[api_name])])
                        not in keywords
                    ):
                        keywords.append(
                            normalize_text(UF_CODE[str(form_data[api_name])])
                        )

                elif data_type in ["select", "select_multiple"]:
                    values = form_data[api_name]
                    keywords = get_complex_translation(snake_field, values, keywords)

                elif data_type == "array_of_objects":
                    new_form_data_list = form_data[api_name]
                    new_form_fields = snake_field["inner_fields"]
                    if isinstance(new_form_data_list, list):
                        for item in new_form_data_list:
                            for new_field in new_form_fields:
                                new_snake_field = keys_to_snake_case(new_field)
                                if (
                                    "api_name" in new_snake_field
                                    and "data_type" in new_snake_field
                                ):
                                    new_api_name = to_snake_case(
                                        new_snake_field["api_name"]
                                    )
                                    new_data_type = new_snake_field["data_type"]
                                    if new_api_name in item:
                                        if (
                                            new_data_type not in need_translation
                                            and normalize_text(item[new_api_name])
                                            not in keywords
                                        ):
                                            keywords.append(
                                                normalize_text(item[new_api_name])
                                            )

                                        elif new_data_type in [
                                            "select",
                                            "select_multiple",
                                        ]:
                                            new_values = item[new_api_name]
                                            keywords = get_complex_translation(
                                                new_snake_field,
                                                new_values,
                                                keywords,
                                            )
    return keywords


def create_keywords(form_data, occurrence_type, reporting=None):
    """
    Since we dont know all the keys that are present in form_data field
    and some keys have values that need translation, the idea here
    is to always update the keywords field with all possible strings
    that can be extracted from form_data and then just include this
    keywords field in the SearchVector.

    Now expanded to include additional searchable fields from the reporting model
    for better search performance without needing complex CONCAT operations.
    """
    keywords = []

    if not occurrence_type:
        return

    if form_data and occurrence_type.form_fields:
        if "fields" in occurrence_type.form_fields:
            fields = occurrence_type.form_fields["fields"]
            keywords = get_translation(form_data, fields, keywords)

    # Add additional searchable data if reporting object is provided
    if reporting:
        # Add reporting number
        if reporting.number:
            normalized_number = normalize_text(reporting.number)
            if normalized_number not in keywords:
                keywords.append(normalized_number)

        # Add occurrence type name
        if occurrence_type and occurrence_type.name:
            normalized_name = normalize_text(occurrence_type.name)
            if normalized_name not in keywords:
                keywords.append(normalized_name)

        # Add road name
        if reporting.road and reporting.road.name:
            normalized_road = normalize_text(reporting.road.name)
            if normalized_road not in keywords:
                keywords.append(normalized_road)

        # Add road name field (backup)
        if reporting.road_name:
            normalized_road_name = normalize_text(reporting.road_name)
            if normalized_road_name not in keywords:
                keywords.append(normalized_road_name)

        # Add km as string
        if reporting.km:
            normalized_km = normalize_text(str(reporting.km))
            if normalized_km not in keywords:
                keywords.append(normalized_km)

    return " ".join(keywords)


def create_involved_parts_keywords(company, involved_parts):
    keywords = []

    possible_path_parts = (
        "occurrencerecord__fields__involvedparts__selectoptions__options"
    )
    parts = get_obj_from_path(company.custom_options, possible_path_parts)
    parts_translation = {item["value"]: item["name"] for item in parts} if parts else {}

    possible_path_fields = "occurrencerecord__fields__involvedpartsfields"
    fields = get_obj_from_path(company.custom_options, possible_path_fields)

    for item in involved_parts:
        if "involved_parts" in item and item["involved_parts"] in parts_translation:
            normalized_part = normalize_text(parts_translation[item["involved_parts"]])
            if normalized_part not in keywords:
                keywords.append(normalized_part)
        keywords = get_translation(item, fields, keywords)

    return " ".join(keywords)


def get_field_by_members(members, form_fields) -> List[dict]:
    fields = form_fields.get("fields", [])
    data_fields = []
    for field in fields:
        if field["id"] in members:
            data_fields.append(field)
    return data_fields


def get_field_representation(field, form_data):
    """
    Check the type of the field_type variable.
    According to the type, get the corresponding display_name and display_value.
    When the type is a array, call this function recursively to get the display_name and display_value of each item in the list.
    """
    field = keys_to_snake_case(field)

    values = []
    field_type = field.get("data_type")
    api_name = to_snake_case(field.get("api_name"))
    display_name = field["display_name"]
    display_value = form_data.get(api_name, "")

    # Handle each field type
    if field_type == "arrayOfObjects":
        for index, data in enumerate(form_data.get(api_name, [])):
            # For each object in the list, manipulate the form_data
            manipulated_form_data = {}
            for key, value in data.items():
                manipulated_key = to_snake_case(key)
                manipulated_form_data[manipulated_key] = value

            # Now, we call recursively passing the manipulated form_data
            inner_field_values = []
            for inner_field in field.get("inner_fields"):
                inner_field_values.extend(
                    get_field_representation(inner_field, manipulated_form_data)
                )

            # Push to values
            values.append(
                {
                    "group_index": index + 1,
                    "data": inner_field_values,
                }
            )
    elif field_type == "boolean":
        if not api_name.startswith("display_"):
            values.append(
                {
                    "display_name": display_name,
                    "display_value": "Sim" if display_value else "Não",
                }
            )
    elif field_type == "select":
        value_form_data = ""
        if form_data.get(api_name):
            value_form_data = form_data[api_name]

        display_value = next(
            (
                option["name"]
                for option in get_obj_from_path(field, "select_options__options")
                if option["value"] == value_form_data
            ),
            None,
        )
        values.append(
            {
                "display_name": display_name,
                "display_value": display_value,
            }
        )
    elif field_type == "selectMultiple":
        value_form_data = ""
        if form_data.get(api_name):
            value_form_data = form_data[api_name]

        display_values = []
        for val in value_form_data:
            display_value = next(
                (
                    option["name"]
                    for option in field["select_options"]["options"]
                    if option["value"] == val
                ),
                None,
            )
            display_values.append(display_value)

        values.append(
            {
                "display_name": display_name,
                "display_value": display_value,
            }
        )
    else:
        values.append(
            {
                "display_name": display_name,
                "display_value": display_value,
            }
        )

    return values


def get_context_in_form_data_to_reports(form_data, form_fields):
    if not form_fields or not form_data:
        return

    data = {"labels": {}}
    generic_fields = []

    if form_data and form_fields:
        for group in form_fields["groups"]:
            group_data = {"name": group["display_name"], "fields": []}
            for field_id in group["members"]:
                # Get field information from memberss
                field_definition = None
                for f in form_fields["fields"]:
                    if f["id"] == field_id:
                        field_definition = f
                        break

                group_data["fields"].extend(
                    get_field_representation(field_definition, form_data)
                )

            generic_fields.append(group_data)

        is_hidrology_information = form_data.get("include_hydrology")
        data["is_hidrology_information"] = is_hidrology_information
        if is_hidrology_information:
            data_hydrology = form_data.get("engie_hidrologia", None)
            if data_hydrology:
                data.update({"engie_hidrologia": {}})
                data_hydrology = keys_to_snake_case(data_hydrology)
                for k, v in data_hydrology.items():
                    if k == "perc_vol_util":
                        data["engie_hidrologia"][
                            k
                        ] = f"{(float(data_hydrology[k])):.2f}"
                    elif k == "data_hora":
                        if "." in v:
                            new_value = v.split(".")[0]
                        else:
                            new_value = v
                        data["engie_hidrologia"][k] = datetime.strptime(
                            new_value, "%Y-%m-%d %H:%M:%S"
                        )
                    else:
                        data["engie_hidrologia"][k] = data_hydrology[k]

    data["generic_fields"] = generic_fields
    return data


def get_context_in_involved_parts_to_reports(involved_parts, company_custom_options):
    if not involved_parts or not company_custom_options:
        return []

    generic_fields = []

    if involved_parts and company_custom_options:
        involved_parts_fields = get_obj_from_path(
            company_custom_options, "occurrencerecord__fields__involvedpartsfields"
        )
        involved_parts_array_field = {
            "data_type": "arrayOfObjects",
            "inner_fields": involved_parts_fields,
            "display_name": "Partes envolvidas",
            "api_name": "involved_parts",
        }

        group_data = {"name": "Partes envolvidas", "fields": []}

        group_data["fields"].extend(
            get_field_representation(
                involved_parts_array_field, {"involved_parts": involved_parts}
            )
        )

        generic_fields.append(group_data)

    return generic_fields


def settings_fields_in_context(context: dict) -> dict:
    data = {}
    data["is_map"] = True if context.get("legend_map", None) else False
    context.update(data)
    return context
