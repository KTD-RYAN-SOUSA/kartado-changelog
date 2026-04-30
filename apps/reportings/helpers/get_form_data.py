from helpers.strings import deep_keys_to_snake_case, to_snake_case


# TODO: Precisa ser aperfeiçoado com campos de inner_fields
def get_value_in_form_fields(field, value, _form_fields):
    fields = deep_keys_to_snake_case(_form_fields.get("fields", []))
    if field == "treatment_images":
        from apps.reportings.models import ReportingFile

        _files = [x.upload.url for x in ReportingFile.objects.filter(pk__in=value)]
        return _files

    for _field in fields:
        api_name = to_snake_case(_field.get("api_name", ""))
        if field == api_name:
            _field_type = to_snake_case(_field.get("data_type"))
            if _field_type in ["string", "number", "float", "text_area", "boolean"]:
                return value
            elif _field_type == "select":
                options = _field.get("select_options", {}).get("options", [])
                for option in options:
                    if str(value) == str(option.get("value", "")):
                        return option.get("name")
                continue
            elif _field_type == "select_multiple":
                options = _field.get("select_options", {}).get("options", [])
                list_option = []
                for option in options:
                    if isinstance(value, str):
                        if str(value) == str(option.get("value", "")):
                            return option.get("name")
                    elif isinstance(value, list):
                        for _v in value:
                            if str(_v) == str(option.get("value", "")):
                                list_option.append(option.get("name"))
                        return list_option

                continue

            elif _field_type == "array_of_objects":
                list_option = []
                if field == "therapy":
                    from apps.occurrence_records.models import OccurrenceType

                    for _v in value:
                        occurrence_type_pk = _v.get("occurrence_type")
                        if occurrence_type_pk:
                            form_fields = OccurrenceType.objects.get(
                                pk=occurrence_type_pk
                            ).form_fields
                            form_data = _v.copy() or {}

                            for k, v in form_data.items():
                                form_data[k] = (
                                    get_value_in_form_fields(k, v, form_fields) or v
                                )
                            list_option.append(form_data)

                else:
                    options = _field.get("inner_fields", [])
                    for option in options:
                        if isinstance(value, list):
                            if (
                                to_snake_case(option.get("data_type"))
                                == "inner_images_array"
                            ):
                                from apps.reportings.models import ReportingFile

                                for _v in value:
                                    if _v:
                                        if isinstance(_v, dict):
                                            if str(list(_v)[0]) == to_snake_case(
                                                option.get("api_name", "")
                                            ):
                                                for __k, __v in _v.items():
                                                    if isinstance(__v, list):
                                                        _files = [
                                                            x.upload.url
                                                            for x in ReportingFile.objects.filter(
                                                                pk__in=__v
                                                            )
                                                        ]
                                                        _v[__k] = _files
                                        list_option.append(_v)

                if len(list_option) != len(value):
                    return

                return list_option
            print(_field_type)
