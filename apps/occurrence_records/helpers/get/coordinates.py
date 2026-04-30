from typing import List


def get_default_coordinates(coordinates, reverse_coordinates):
    if reverse_coordinates:
        args_coordinates = [coordinates[1], coordinates[0]]
    else:
        args_coordinates = [coordinates[0], coordinates[1]]

    return args_coordinates


def build_list_coordinates_in_properties(
    coordinates: (tuple, list), reverse_coordinates
):
    list_coordinates = []

    args_coordinates = get_default_coordinates(coordinates, reverse_coordinates)

    if isinstance(coordinates, (tuple, list)):
        if (
            len(coordinates) == 2
            and isinstance(coordinates[0], (int, float))
            and isinstance(coordinates[1], (int, float))
        ):
            return args_coordinates

    return list_coordinates


def get_list_coordinates_in_properties(lat_log: list, reverse_coordinates):
    try:
        expectation = build_list_coordinates_in_properties(lat_log, reverse_coordinates)
        if expectation:
            return expectation

    except Exception as e:
        print(">>>>>>>>>>>>>>> get_list_coordinates_in_properties", e)
        return


def find_min_elevation(
    elevation_data: list or List[list], logs_lats_clean: List[list], reverse_coordinates
) -> int:
    for long_lat in logs_lats_clean:
        args_coordinates = get_default_coordinates(long_lat, not reverse_coordinates)

        if elevation_data[:2] == args_coordinates:
            if len(long_lat) > 2:
                return long_lat[-1]

    raise ValueError(
        "kartado.error.occurrence_record.set_altimetry.reverse_coordinates"
    )
