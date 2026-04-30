from helpers.strings import to_snake_case


def get_relationships_attributes_from_response(response):
    relations = []
    for rel in response["data"]["relationships"].keys():
        relations.append(to_snake_case(rel))
    return relations


def get_attributes_from_response(response):
    attrs = []
    for attr in response["data"]["attributes"].keys():
        attrs.append(to_snake_case(attr))
    return attrs


def validate_response(expect_response, response):
    relations = get_relationships_attributes_from_response(response)
    attributes = get_attributes_from_response(response)
    return (
        relations == expect_response["relations"]
        and attributes == expect_response["attributes"]
    )


def response_has_object(response, obj_uuid):
    # check if response has a especific uuid (only for list action)

    has_object = False
    for obj_data in response["data"]:
        if obj_data["id"] == obj_uuid:
            has_object = True
            break
    return has_object
