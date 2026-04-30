import json
from collections import OrderedDict
from copy import deepcopy
from typing import Any, List, Tuple, Union

from json_logic import jsonLogic

from apps.companies.models import Company
from helpers.json_parser import JSONRenderer
from helpers.strings import get_obj_from_path


def apply_reporting_json_logic(reporting, formula):
    from apps.reportings.serializers import ReportingSerializer
    from apps.reportings.views import ReportingView

    try:
        # To ensure formula compatibility between front and backend,
        # invoke the renderer to get the JSON just like the frontend does
        data = json.loads(
            JSONRenderer().render(
                ReportingSerializer(reporting).data,
                renderer_context={"view": ReportingView},
            )
        )
        data = {
            "relationships": data["data"]["relationships"],
            **data["data"]["attributes"],
        }

        amount = apply_json_logic(formula, data)
        # make sure the jsonLogic result is valid and a number
        if not isinstance(amount, (int, float)):
            raise Exception()
    except Exception:
        return 0
    else:
        return amount


def get_fields_options(
    form_fields: list, company: Union[Company, None] = None
) -> OrderedDict:
    """
    Using the raw form_fields from the OccurrenceType, build a reference dict that
    contains the options for each field for easy indexing.

    Dict structure:
        - Select field: api_name -> option_name -> option_value
        - ArrayOfObjects field: outer_api_name.inner_api_name -> option_name -> option_value

    Assumes camelCase.

    Args:
        form_fields (list): The content of OccurrenceType.form_fields.

    Returns:
        Dict[str, Dict[str, str]]: A reference dict with fields pointing to options.
    """
    from apps.occurrence_records.models import OccurrenceType

    field_to_options = OrderedDict()

    first_path = "selectoptions"

    for field in form_fields:
        api_name = field["apiName"]
        data_type = field["dataType"]

        if data_type in ["select", "selectMultiple"]:
            select_options = get_obj_from_path(field, first_path)
            if "reference" not in select_options:
                second_path = "options"
                field_to_options[f"{api_name}"] = {
                    option["name"]: option["value"]
                    for option in get_obj_from_path(select_options, second_path)
                }
            else:
                second_path = "reference"
                options = get_obj_from_path(select_options, second_path)
                if company and options["resource"] == "OccurrenceType":
                    database_values = OccurrenceType.objects.filter(
                        company=company
                    ).values(options["optionText"], options["optionValue"])
                    field_to_options[f"{api_name}"] = {
                        str(option[options["optionText"]]): str(
                            option[options["optionValue"]]
                        )
                        for option in database_values
                    }

        if data_type == "arrayOfObjects":
            inner_fields: list = field["innerFields"]
            inner_fields_to_options: dict = get_fields_options(inner_fields, company)
            field_to_options.update(
                {
                    f"{api_name}.{inner_api_name}": inner_options
                    for inner_api_name, inner_options in inner_fields_to_options.items()
                }
            )

    return field_to_options


def build_updated_logic(
    logic: dict,
    fields_to_options: dict,
    data: dict,
    form_fields: list,
    var_names: list,
) -> dict:
    """
    Using a reference dict of field options, rebuild the provided logic dict
    where varName calls will be switched to var references accessing the correct match.

    Args:
        logic (dict): Original dict with varName mentions
        fields_to_options (dict): Reference dict built using get_fields_options()
        data (dict): Updated data containing varNamesOp data to allow var access
        form_fields (list): List with all fields inside a OccurrenceType
        var_names (List[str]): List with all mentioned fields

    Returns:
        dict: Updated logic with all varName handled.
    """

    SUB_KEY = "varName"
    REDUCE_KEY = "reduce"

    if isinstance(logic, dict):
        result = {}
        form_data = data["formData"]

        for key, value in logic.items():
            # Substitute the SUB_KEY with the generated logic
            if key == SUB_KEY:
                req_field_key = value.replace("formData.", "")
                is_array_of_objects = len(req_field_key.split(".")) > 1

                # Field will be skiped
                if req_field_key not in fields_to_options:
                    continue

                # dataType == arrayOfObjects
                if is_array_of_objects:
                    field_name, req_inner_field_name = req_field_key.split(".")
                    field_value = form_data[field_name]
                    result["merge"] = []
                    for item in field_value:
                        inner_field_list = []
                        for inner_field_name, inner_field_value in item.items():
                            if inner_field_name == req_inner_field_name:
                                inner_field_var = {
                                    "var": f"varNamesOp.{req_field_key.replace('.', '>')}<{inner_field_value}>"
                                }
                                inner_field_list.append(inner_field_var)

                        result["merge"].append([inner_field_list])

                # dataType == select
                else:
                    field_value = form_data[req_field_key]
                    result["var"] = f"varNamesOp.{req_field_key}<{field_value}>"
            elif key == REDUCE_KEY:
                result[key] = call_reduce_logic(
                    logic, form_fields, fields_to_options, var_names
                )
            else:
                result[key] = build_updated_logic(
                    value, fields_to_options, data, form_fields, var_names
                )

        return result
    elif isinstance(logic, list):
        return [
            build_updated_logic(item, fields_to_options, data, form_fields, var_names)
            for item in logic
        ]
    else:
        return logic


def process_fields_values(
    field_name: str, var_names: List[str], actual_fields: list, fields_to_options: dict
) -> List[Tuple[str, dict, bool]]:
    """
    Returns a list of tuples with informations about each varName.

    Args:
        field_name (str): apiName of arraOfObjects used in logic
        var_names (List[str]): List with all mentioned fields
        actual_fields (list): Fields that are inside arrayOfObjects field
        fields_to_options (dict): A reference dict with fields pointing to options

    Returns:
        List[Tuple[str, dict, bool]]: List of tuples with informations about the
        referenced varNames. Each tuple contains:
        - The varName itself;
        - A dict with names and values of the varName
        - Flag to see if the field's dataType is selectMultiple or not
    """
    process_fields = []
    if var_names:
        for var_name in var_names:
            api_name = var_name.split(".")[1]
            field_array = next(
                item for item in actual_fields if item["apiName"] == api_name
            )
            is_select_multiple = field_array.get("dataType") == "selectMultiple"
            option_values = next(
                (
                    v
                    for k, v in fields_to_options.items()
                    if k == f"{field_name}.{api_name}"
                ),
                {},
            )
            process_fields.append((var_name, option_values, is_select_multiple))
    return process_fields


def construction_if_structures(process_fields: List[Tuple[str, dict, bool]]) -> dict:
    """
    Build structures that will replace varName fields inside the logic.

    Args:
        process_fields (List[Tuple[str, dict, bool]]): List of tuples with informations
        about the referenced varNames

    Returns:
        dict: A dict with a constructed if structure that will replace varName fields
        inside the reduce-type logic
    """
    if_structures = {}
    for index, (var_name, options_values, is_select_multiple) in enumerate(
        process_fields
    ):
        if is_select_multiple:
            result = {"cat": [""]}
            for name, value in options_values.items():
                result["cat"].append(
                    {
                        "if": [
                            {"in": [value, {"var": var_name}]},
                            f"{name.strip()}; ",
                            "",
                        ],
                    }
                )
            if_structures[f"field{str(index+1)}"] = result
        else:
            result = {"if": []}
            for name, value in options_values.items():
                result["if"].append({"==": [{"var": var_name}, value]})
                result["if"].append(name.strip())
            result["if"].append("")
            if_structures[f"field{str(index+1)}"] = result
    return if_structures


def replace_var_name_with_structure(
    cat_item: Union[list, str, dict, int, float],
    field_index_ref: dict,
    if_structures: dict,
) -> Union[list, str, dict, int, float]:
    """
    Replace the necessary items (with varName in it), no matter the depth

    Args:
        cat_item (Union[list, str, dict, int, float]): The item inside the logic that
        will be replaced, if necessary
        field_index_ref (dict): Used as a key to each cat_item constructed inside
        if_structures dict
        if_structures (dict): A dict with a constructed if structure that will replace
        varName fields inside the reduce-type logic

    Returns:
        Union[list, str, dict, int, float]: Returns the handled item inside the logic,
        according to it's type
    """
    if isinstance(cat_item, dict) and "varName" in cat_item:
        field_key = f'field{field_index_ref["index"]}'
        if_structure = if_structures[field_key]
        field_index_ref["index"] += 1
        return if_structure if if_structure else cat_item
    elif isinstance(cat_item, dict) and "if" in cat_item:
        new_cat = deepcopy(cat_item)
        new_cat.update(
            {
                "if": [
                    replace_var_name_with_structure(
                        sub_item, field_index_ref, if_structures
                    )
                    for sub_item in cat_item["if"]
                ]
            }
        )
        return new_cat
    elif isinstance(cat_item, dict) and "cat" in cat_item:
        new_cat = deepcopy(cat_item)
        new_cat.update(
            {
                "cat": [
                    replace_var_name_with_structure(
                        sub_item, field_index_ref, if_structures
                    )
                    for sub_item in cat_item["cat"]
                ]
            }
        )
        return new_cat
    elif isinstance(cat_item, list):
        return [
            replace_var_name_with_structure(sub_item, field_index_ref, if_structures)
            for sub_item in cat_item
        ]
    else:
        return cat_item


def reduce_logic(logic: dict, if_structures: dict) -> dict:
    """
    Replace all instances of varName inside the logic with the constructed if structure.

    Args:
        logic (dict): Original dict with varName mentions
        if_structures (dict): A dict with a constructed if structure that will replace
        varName fields inside the reduce-type logic

    Returns:
        dict: Updated logic with all varName handled
    """
    logic_reduce = logic.get("reduce")
    for reduce_item in logic_reduce:
        if "if" in reduce_item and reduce_item["if"]:
            new_if = []
            for if_item in reduce_item["if"]:
                if "cat" in if_item and if_item["cat"]:
                    field_index_ref = {"index": 1}
                    new_cat = []
                    for cat_item in if_item["cat"]:
                        cat_item = replace_var_name_with_structure(
                            cat_item, field_index_ref, if_structures
                        )
                        new_cat.append(cat_item)
                    if_item["cat"] = new_cat
                new_if.append(if_item)
            reduce_item["if"] = new_if
    return logic


def call_reduce_logic(
    logic: dict, form_fields: list, fields_to_options: dict, var_names: List[str]
) -> list:
    """
    Change all varName fields inside reduce-type logic, no matter the depth.

    Args:
        logic (dict): Original dict with varName mentions
        form_fields (list): List with all fields inside a OccurrenceType
        fields_to_options (dict): A reference dict with fields pointing to options
        var_names (List[str]): List with all mentioned fields

    Returns:
        list: Updated reduce logic with all varName handled.
    """
    logic_reduce = logic.get("reduce")
    if logic_reduce and isinstance(logic_reduce, list):
        new_items = []
        for item in logic_reduce:
            if not isinstance(item, dict):
                continue
            if "var" in item and item["var"]:
                new_items.append(item["var"])
            elif "if" in item and item["if"]:
                for sub_item in item["if"]:
                    if "var" in sub_item and sub_item["var"]:
                        new_items.append(sub_item["var"])
        if not new_items:
            return logic_reduce
        get_form_data_var = list(
            filter(lambda a: a.startswith("formData."), new_items)
        )[0]
        field_name = get_form_data_var.split(".")[1]
        actual_fields = next(
            item["innerFields"] for item in form_fields if item["apiName"] == field_name
        )
        process_fields = process_fields_values(
            field_name, var_names, actual_fields, fields_to_options
        )
        if_structures = construction_if_structures(process_fields)
        logic_var_name_reduce = reduce_logic(logic, if_structures)

        return logic_var_name_reduce.get("reduce", [])


def find_var_name_values(logic: dict) -> List[str]:
    """
    Returns a list with all the requested values inside varName operations.

    Args:
        logic (dict): The logic where we'll look for varName calls

    Returns:
        List[str]: List with all mentioned fields
    """

    key = "varName"
    values = []

    if isinstance(logic, dict):
        for k, v in logic.items():
            if k == key:
                values.append(v)
            if isinstance(v, (dict, list)):
                values.extend(find_var_name_values(v))
    elif isinstance(logic, list):
        for item in logic:
            if isinstance(item, (dict, list)):
                values.extend(find_var_name_values(item))
    return values


def update_data_with_possibilities(
    data: dict, logic: dict, fields_to_options: dict
) -> Tuple[dict, List[str]]:
    """
    Builds a new data dict with all possibilities for the mentioned varNames.

    Args:
        data (dict): The input data to be processed
        logic (dict): We need to logic to look for varName mentions
        fields_to_options (dict): A reference dict with fields pointing to options

    Returns:
        new_data (dict): Updated data argument with all possibilities for each varName field
        var_names (List[str]): List with all mentioned fields
    """

    new_data = deepcopy(data)
    var_names = find_var_name_values(logic)

    if var_names:
        var_names_op = {}
        for var_name in var_names:
            clean_var_name_field = var_name.replace("formData.", "")
            is_array_of_objs = len(clean_var_name_field.split(".")) > 1

            field_options = fields_to_options.get(clean_var_name_field, None)
            if field_options:
                for field_name, field_value in field_options.items():
                    if is_array_of_objs:
                        new_key = (
                            f"{clean_var_name_field.replace('.', '>')}<{field_value}>"
                        )
                    else:
                        new_key = f"{clean_var_name_field}<{field_value}>"

                    var_names_op[new_key] = field_name

        new_data["varNamesOp"] = var_names_op

    return new_data, var_names


def apply_json_logic(
    logic: dict, data: dict, occurrence_type=None, company=None
) -> Any:
    """
    If a OccurrenceType and Company is provided, the varName usage will be automatically updated to
    a if clause using each field options. Otherwise the regular jsonLogic call will be applied.

    Args:
        logic (dict): The json logic dict (will be updated if occurrence_type usage)
        data (dict): Data to feed the logic dict
        occurrence_type (Union[OccurrenceType, None], optional): The OccurrenceType where we'll fetch
        the form_fields. Defaults to None.
        company (Union[Company, None], optional): The Company where we'll fetch
        the reference values. Defaults to None.

    Returns:
        Any: The result of the applied json logic
    """

    if occurrence_type and company and isinstance(logic, dict):
        form_fields = get_obj_from_path(occurrence_type.form_fields, "fields")
        fields_to_options = get_fields_options(form_fields, company)
        updated_data, var_names = update_data_with_possibilities(
            data, logic, fields_to_options
        )
        updated_logic = build_updated_logic(
            logic, fields_to_options, updated_data, form_fields, var_names
        )

        return jsonLogic(updated_logic, updated_data)
    else:
        return jsonLogic(logic, data)
