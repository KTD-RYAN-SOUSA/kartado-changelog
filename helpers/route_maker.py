import json
from math import sqrt

import googlemaps
from django.contrib.gis.geos import LineString, Point
from geopy.distance import distance, lonlat
from mapbox import Directions
from shapely.geometry import LineString as SHLineString
from shapely.geometry import MultiPoint as SHMultiPoint
from shapely.geometry import Point as SHPoint
from shapely.ops import nearest_points


def chunk_list(length, n):
    # For item i in a range that is a length of l,
    for i in range(0, len(length), n):
        # Create an index range for l of n items:
        yield length[i : i + n]


def line_length(line):
    """Length of a line in meters, given in geographic coordinates

    Args:
        line: a shapely LineString object with WGS-84 coordinates

    Returns:
        Length of line in meters
    """
    return sum(
        (
            sqrt(
                distance(lonlat(a[0], a[1], a[2]), lonlat(b[0], b[1], b[2])).km ** 2
                + ((a[2] / 1000) - (b[2] / 1000)) ** 2
            )
        )
        for (a, b) in pairs(line.coords)
    )


def dic_to_ordered_list(dic):
    """
    Gets dictionary and converts it to sorted list
    """
    lst = []

    keys = list(map(int, dic.keys()))
    order = sorted(keys)

    for n in order:
        dic[str(n)]["key"] = n
        lst.append(dic[str(n)])

    return lst


def pairs(lst):
    """
    Iterate over a list in overlapping pairs without wrap-around.

    Args:
        lst: an iterable/list

    Returns:
        Yields a pair of consecutive elements (lst[k], lst[k+1]) of lst. Last
        call yields the last two elements.

    Example:
        lst = [4, 7, 11, 2]
        pairs(lst) yields (4, 7), (7, 11), (11, 2)
    """
    i = iter(lst)
    prev = i.__next__()
    for item in i:
        yield prev, item
        prev = item


def unequal_point_pairs(lst):
    """
    Iterate over a list in overlapping pairs without wrap-around removing any duplicates

    Args:
        lst: an iterable/list

    Returns:
        Yields a pair of consecutive elements (lst[k], lst[k+1]) of lst. Last
        call yields the last two elements.

    Example:
        lst = [4, 4, 7, 11, 11, 2]
        pairs(lst) yields (4, 7), (7, 11), (11, 2)
    """
    i = iter(lst)
    prev = i.__next__()
    for item in i:
        if prev is not item:
            yield prev, item
        prev = item


class Router:
    """
    Class used to make the path for the roads in the system
    It uses the API from MapBox to create the full path by using the driving profile,
    while the API from GoogleMaps is used to calculate the elevation for each point in the path.

    There is also a boolean field called "manual_road" that, if is True, will not be calculating the middle
    points from the marks and will only use the same marks to make the path. This is used when constructing
    roads that still doesn't exist in the MapBox API.
    """

    def __init__(self, GMAPS_API_KEY, MAPBOX_API_KEY, manual_road):
        self.GoogleMaps = googlemaps.Client(key=GMAPS_API_KEY)
        self.MapBoxRoadMaps = Directions(access_token=MAPBOX_API_KEY)
        self.manual_road = manual_road
        self.marks = None
        self.dict_mark = None
        self.path = None
        self.length = None

    def set_marks(self, marks):
        self.dict_mark = marks
        self.marks = dic_to_ordered_list(marks)

    def get_raw_route_points(self):
        """
        Get route with maximum available resolution and return route points
        """
        unordered_coordinates = []

        # Generate pair with start and finish points
        route = [
            a["point"] for a in self.marks if "mapbox_call" in a and a["mapbox_call"]
        ]
        if len(route) == 0:
            route = [self.marks[0]["point"], self.marks[-1]["point"]]

        if not self.manual_road:
            response = self.MapBoxRoadMaps.directions(
                route, "mapbox/driving", geometries="geojson", overview="full"
            )
            geojson = json.loads(response.content)
            route_geometry = geojson["routes"][0]["geometry"]

            # Add provider points
            for item in route_geometry["coordinates"]:
                unordered_coordinates.append(SHPoint(item[1], item[0]))

        # Add manual mark points
        for item in self.marks:
            unordered_coordinates.append(
                SHPoint(
                    item["point"]["coordinates"][1],
                    item["point"]["coordinates"][0],
                )
            )

        # Order points
        coordinates = []

        if not self.manual_road:
            collection = SHMultiPoint(unordered_coordinates)
        else:
            collection = SHLineString(unordered_coordinates)

        first_point = SHPoint(
            self.marks[0]["point"]["coordinates"][1],
            self.marks[0]["point"]["coordinates"][0],
        )
        # first_point_on_line = nearest_points(collection, first_point)[0]
        coordinates.append([first_point.coords.xy[0][0], first_point.coords.xy[1][0]])

        if not self.manual_road:
            lst = list(collection.geoms)
            lst.remove(first_point)
            collection = SHMultiPoint(lst)
        else:
            collection = SHMultiPoint(unordered_coordinates)
        next_point = first_point

        while len(collection) > 1:
            next_point = nearest_points(collection, next_point)[0]
            coordinates.append([next_point.coords.xy[0][0], next_point.coords.xy[1][0]])
            lst = list(collection.geoms)
            lst.remove(next_point)
            collection = SHMultiPoint(lst)

        last_mark = self.marks[-1]["point"]["coordinates"][::-1]
        if last_mark not in coordinates:
            coordinates.append(last_mark)

        for item in self.dict_mark.keys():
            try:
                coords = self.dict_mark[item]["point"]["coordinates"].copy()
                coords.reverse()
                self.dict_mark[item]["index"] = coordinates.index(coords)
            except Exception as e:
                print(item)
                print(e)

        return coordinates

    def get_points_with_elevation(self, points):
        direction_with_elevation = []

        # Google Elevation API accepts only 512 points per request
        points_pagination = chunk_list(points, 400)
        for page in points_pagination:
            direction_with_elevation += self.GoogleMaps.elevation(page)

        points = []
        for item in direction_with_elevation:
            points.append(
                Point(
                    item["location"]["lng"],
                    item["location"]["lat"],
                    item["elevation"],
                    srid=4326,
                )
            )
        return points

    def make_route(self):
        try:
            # Get data from providers
            raw_points = self.get_raw_route_points()
            route_points = self.get_points_with_elevation(raw_points)

            # Make linestring
            self.path = LineString(route_points)
            self.path.srid = 4326

            # Calculate length
            self.length = line_length(self.path)

            return True
        except Exception as e:
            print(e)
            return False
