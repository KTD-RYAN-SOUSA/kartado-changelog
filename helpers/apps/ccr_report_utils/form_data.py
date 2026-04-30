import json
from typing import Dict, List

from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting
from helpers.strings import get_obj_from_path, to_flatten_str, to_snake_case


def new_get_form_data(
    reporting: Reporting,
    api_path: str,
    name_path: str = None,
    default=None,
    raw: bool = False,
):
    """
    Get form data using double underscore notation as the
    nested lookup syntax (just like in Django)
    """
    data = None
    try:
        field: dict = reporting.occurrence_type.form_fields["fields"]
        form_data: dict = reporting.form_data
        data = get_inner_data(form_data, field, api_path, name_path, default, raw)
    except Exception:
        pass
    return data


def get_occurrence_kind_reference_options(
    reporting: Reporting, api_path: str
) -> Dict[str, str]:
    api_list = api_path.split("__")
    options = {}
    try:
        fields: dict = reporting.occurrence_type.form_fields["fields"]
        reference_field = None
        i = 0
        while fields is not None:
            if to_flatten_str(fields[i]["apiName"]) == to_flatten_str(api_list[0]):
                api_list.pop(0)
                reference_field = fields[i]
                if len(api_list) == 0:
                    reference_field = fields[i]
                    break
                fields = fields[i].get("innerFields")
                i = 0
                continue
            i += 1

        reference = reference_field["selectOptions"]["reference"]
        filter_str = reference.get("filter")
        resource = reference.get("resource")
        option_text = reference.get("optionText")
        option_value = reference.get("optionValue")
        if filter_str is not None and resource == "OccurrenceType":
            filter = json.loads(filter_str)
            occurrence_kind = filter.get("occurrence_kind", None)
            occurrence_types: List[OccurrenceType] = list(
                OccurrenceType.objects.filter(occurrence_kind__in=occurrence_kind)
            )
            options = {
                str(getattr(occ_type, option_value)): str(
                    getattr(occ_type, option_text)
                )
                for occ_type in occurrence_types
            }
    except Exception:
        pass
    return options


def get_inner_data(
    form_data: dict,
    field: dict,
    api_path: str,
    name_path: str = None,
    default=None,
    raw=False,
):
    """
    Get form data using double underscore notation as the
    nested lookup syntax (just like in Django)
    """
    try:
        api_list = api_path.split("__")
        name_list: List[str] = None

        if name_path is None:
            name_list = list(map(to_snake_case, api_list))
        else:
            name_list = name_path.split("__")
        data = None

        api_it = iter(api_list)
        name_it = iter(name_list)
        api = to_flatten_str(next(api_it, ""))
        name = to_flatten_str(next(name_it, ""))
        is_array = False
        while True:
            is_array = api.isnumeric()
            if is_array:
                form_data = form_data[int(name)]
            else:
                field = next(
                    in_field
                    for in_field in field
                    if to_flatten_str(in_field.get("apiName", "")) == api
                )
                form_data = next(
                    form_data[in_data]
                    for in_data in form_data.keys()
                    if to_flatten_str(in_data) == name
                )

            api = to_flatten_str(next(api_it, ""))
            name = to_flatten_str(next(name_it, ""))
            if api == "" or name == "":
                break
            elif not is_array:
                field = field.get("innerFields")

        value = form_data

        if not raw:
            field_type = str()
            if not is_array:
                field_type: str = field.get("dataType", None)
            if field_type == "select":
                options = field.get("selectOptions").get("options")
                my_option = next(
                    option for option in options if option["value"] == value
                )
                value = my_option["name"]

            elif field_type == "selectMultiple":
                options = field.get("selectOptions").get("options")
                my_options = [
                    option["name"] for option in options if option["value"] in value
                ]
                value = my_options

        data = value
    except Exception:
        data = default

    return data


class FormArrayIterator(object):
    def __init__(self, field: dict, form_data: dict) -> None:
        self.field = field["innerFields"]
        self.form_data = form_data

        self.data_it = iter(self.form_data)
        self.__curr_data = next(self.data_it)

    def get(
        self,
        api_path: str,
        name_path: str = None,
        default=None,
        raw=False,
    ) -> object:
        return get_inner_data(
            self.__curr_data, self.field, api_path, name_path, default=default, raw=raw
        )

    def inc(self) -> None:
        self.__curr_data = next(self.data_it)


def get_form_array_iterator(
    reporting: Reporting,
    api_path: str,
    name_path: str = None,
    default=None,
) -> FormArrayIterator:
    """
    Get form data using double underscore notation as the
    nested lookup syntax (just like in Django)
    """
    data = None
    try:
        api_list = api_path.split("__")
        name_list: List[str] = None

        if name_path is None:
            name_list = list(map(to_snake_case, api_list))
        else:
            name_list = name_path.split("__")

        field: dict = reporting.occurrence_type.form_fields["fields"]

        form_data: dict = reporting.form_data

        api_it = iter(api_list)
        name_it = iter(name_list)
        api = to_flatten_str(next(api_it, ""))
        name = to_flatten_str(next(name_it, ""))
        while True:
            is_array = api.isnumeric()
            if is_array:
                form_data = form_data[int(name)]
            else:
                field = next(
                    in_field
                    for in_field in field
                    if to_flatten_str(in_field.get("apiName", "")) == api
                )
                form_data = next(
                    form_data[in_data]
                    for in_data in form_data.keys()
                    if to_flatten_str(in_data) == name
                )

            api = to_flatten_str(next(api_it, ""))
            name = to_flatten_str(next(name_it, ""))
            if api == "" or name == "":
                break
            elif not is_array:
                field = field.get("innerFields")

        return FormArrayIterator(field, form_data)
    except Exception:
        data = default

    return data


def new_get_form_data_selected_option(
    reporting: Reporting,
    api_path: str,
    selected_option,
    default=None,
):
    """
    Get the selected option text from the form data of reporting
    using double underscore notation as the
    nested lookup syntax (just like in Django)
    """
    try:
        api_list = api_path.split("__")

        field: dict = reporting.occurrence_type.form_fields["fields"]

        api_it = iter(api_list)
        api = to_flatten_str(next(api_it, ""))
        while True:
            is_array = api.isnumeric()
            if not is_array:
                field = next(
                    in_field
                    for in_field in field
                    if to_flatten_str(in_field.get("apiName", "")) == api
                )

            api = to_flatten_str(next(api_it, ""))
            if api == "":
                break
            elif not is_array:
                field = field.get("innerFields")

        field_type: str = field.get("dataType", None)
        if field_type in ["select", "selectMultiple"]:
            options = field.get("selectOptions").get("options")
            my_option = next(
                option for option in options if option["value"] == selected_option
            )
            data = my_option["name"]
        else:
            data = default
    except Exception:
        data = default

    return data


def get_form_data(
    reporting: Reporting,
    field_name: str,
    data_name: str = None,
    subgroup: str = None,
    value: str = None,
) -> str:
    try:
        dataname = data_name if data_name else field_name
        form_fields = reporting.occurrence_type.form_fields["fields"]
        if not subgroup:
            form_field = next(
                obj
                for obj in form_fields
                if get_obj_from_path(obj, "apiname") == dataname
            )
        else:
            form_field = next(
                obj
                for obj in form_fields
                if get_obj_from_path(obj, "apiname") == subgroup
            )
            if form_field:
                form_field = next(
                    obj
                    for obj in form_field["innerFields"]
                    if get_obj_from_path(obj, "apiname") == dataname
                )

        if form_field:
            field_type = get_obj_from_path(form_field, "datatype")

            data = reporting.form_data.get(field_name) if not value else value

            if data is None:
                return data

            if field_type in [
                "string",
                "number",
                "float",
                "textArea",
                "arrayOfObjects",
            ]:
                return data

            elif field_type == "select":
                options = get_obj_from_path(form_field, "selectoptions__options")
                my_option = next(a for a in options if a["value"] == data)
                return my_option["name"]
            elif field_type == "selectMultiple":
                options = get_obj_from_path(form_field, "selectoptions__options")
                my_option = [a["name"] for a in options if a["value"] in data]
                return my_option
    except Exception:
        pass
    return None


def remove_old_values_in_form_data(form_data: dict, target: str):
    if isinstance(form_data, dict):
        for key in list(form_data.keys()):
            if isinstance(form_data[key], (dict, list)):
                form_data[key] = remove_old_values_in_form_data(form_data[key], target)
    elif isinstance(form_data, list):
        form_data = [
            remove_old_values_in_form_data(item, target)
            for item in form_data
            if item != target
        ]
    return form_data
