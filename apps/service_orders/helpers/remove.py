def remove_attribute_occupancy(validated_data: dict) -> dict:
    validated_data.pop("obra", None)
    validated_data.pop("sequencial", None)
    validated_data.pop("identificador", None)
    validated_data.pop("offender_name", None)
    return validated_data
