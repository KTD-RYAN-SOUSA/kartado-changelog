# from shapely.geometry import LineString, Point

from django.contrib.gis.geos import LineString, Point
from fnc.mappings import get

from apps.roads.models import Road

from .route_maker import dic_to_ordered_list, unequal_point_pairs


def cut(line, distance):
    # Cuts a line in two at a distance from its starting point
    # This is taken from shapely manual
    if distance <= 0.0 or distance >= line.length:
        return [LineString(line)]
    coords = list(line.coords)
    for i, p in enumerate(coords):
        pd = line.project(Point(p))
        if pd == distance:
            return [LineString(coords[: i + 1]), LineString(coords[i:])]
        if pd > distance:
            cp = line.interpolate(distance)
            return [
                LineString(coords[:i] + [(cp.x, cp.y)]),
                LineString([(cp.x, cp.y)] + coords[i:]),
            ]


def split_line_with_points(line, points):
    """
    Splits a line string in several segments considering a list of points.

    The points used to cut the line are assumed to be in the line string
    and given in the order of appearance they have in the line string.

    >>> line = LineString( [(1,2), (8,7), (4,5), (2,4), (4,7), (8,5), (9,18),
    ...        (1,2),(12,7),(4,5),(6,5),(4,9)] )
    >>> points = [Point(2,4), Point(9,18), Point(6,5)]
    >>> [str(s) for s in split_line_with_points(line, points)]
    ['LINESTRING (1 2, 8 7, 4 5, 2 4)',
    'LINESTRING (2 4, 4 7, 8 5, 9 18)',
    'LINESTRING (9 18, 1 2, 12 7, 4 5, 6 5)',
    'LINESTRING (6 5, 4 9)']
    """
    segments = []
    current_line = line
    for p in points:
        d = current_line.project(p)
        seg, current_line = cut(current_line, d)
        segments.append(seg)
    segments.append(current_line)
    return segments


def km_to_coordinates(road, km):
    """
    Convert km to coordinates
    """
    road_marks = dic_to_ordered_list(road.marks)
    selected_pair = None

    for pair in unequal_point_pairs(road_marks):
        if pair[0]["km"] > km and pair[1]["km"] < km:
            selected_pair = pair
            break
        elif pair[1]["km"] > km and pair[0]["km"] < km:
            selected_pair = pair
            break
        elif pair[0]["km"] == km:
            return Point(pair[0]["point"]["coordinates"]), road
        elif pair[1]["km"] == km:
            return Point(pair[1]["point"]["coordinates"]), road

    # Calculate total length
    start_km = min([selected_pair[0]["km"], selected_pair[1]["km"]])
    end_km = max([selected_pair[0]["km"], selected_pair[1]["km"]])
    segment_mark_length = end_km - start_km
    distance_from_min = km - start_km
    # Check if km is decreasing
    invert_km = selected_pair[1]["km"] <= selected_pair[0]["km"]

    # Cut segment
    start_key = min((selected_pair[0]["index"], selected_pair[1]["index"]))
    end_key = max((selected_pair[0]["index"], selected_pair[1]["index"]))

    points = []
    for key in range(start_key, end_key + 1):
        points.append(Point(road.path[key][0], road.path[key][1], road.path[key][2]))

    segment = LineString(points, srid=4326)
    # Apply km inversion correction
    if invert_km:
        segment_distance = (
            1 - (distance_from_min / segment_mark_length)
        ) * segment.length
    else:
        segment_distance = (distance_from_min / segment_mark_length) * segment.length
    # Find point
    point = segment.interpolate(segment_distance)

    return Point(point.x, point.y), road


def check_valid_road(road, km):
    """
    Checks if specified road has km range.

    For roads marked as default_segment (is_default_segment=True),
    any km is considered valid since they have default marks with
    extreme values (-999999 and 999999).
    """
    # Se a rodovia tem is_default_segment=True, aceita qualquer km
    if hasattr(road, "is_default_segment") and road.is_default_segment:
        return True

    road_marks = dic_to_ordered_list(road.marks)

    for pair in unequal_point_pairs(road_marks):
        if pair[0]["km"] >= km and pair[1]["km"] <= km:
            return True
        elif pair[1]["km"] >= km and pair[0]["km"] <= km:
            return True

    return False


def get_road_coordinates(road_name, km, direction, company):
    # Ensure we are dealing with a float KM
    try:
        float_km = float(km)
    except Exception:
        raise ValueError(
            "The provided km is not a float and could not be converted to one"
        )

    road_set = Road.objects.filter(
        name=road_name, direction=int(direction), company=company
    ).exclude(is_default_segment=True)

    # If roads in specified direction are not found, search road only
    # by name and order then by direction
    road_set_generic = (
        Road.objects.filter(name=road_name, company=company)
        .exclude(is_default_segment=True)
        .order_by("direction")
    )

    # Check if KM range in road_set
    print("Searching KM on direction...")
    valid = False
    for road in road_set:
        if check_valid_road(road, float_km):
            print("Found KM on Road {}".format(road))
            valid = True
            break

    if not valid:
        print("Searching KM without direction...")
        for road in road_set_generic:
            if check_valid_road(road, float_km):
                print("Found KM on Road {}".format(road))
                valid = True
                break

    if not valid:
        return Point(0, 0), None

    try:
        return km_to_coordinates(road, float_km)
    except Exception:
        return Point(0, 0), None


def calculate_end_km(obj, project_km=False):
    use_direction = False

    if project_km:
        km = obj.project_km
    else:
        km = obj.km

    if km is None:
        return km

    if "use_direction" in obj.company.metadata:
        use_direction = obj.company.metadata["use_direction"]

    try:
        length = obj.form_data["length"]
        if type(length) is str:
            length = float(length)
        length = length / 1000
    except Exception:
        length = 0

    if use_direction:
        falling_direction = get("metadata.direction.falling", obj.road, default="0")
        rising_direction = get("metadata.direction.rising", obj.road, default="1")
        if obj.direction == falling_direction:
            end_km = km - length
        elif obj.direction == rising_direction:
            end_km = km + length
        else:
            end_km = km
    else:
        end_km = km + length

    if end_km and end_km < 0:
        end_km = 0

    return end_km
