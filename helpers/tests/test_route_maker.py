from unittest.mock import Mock, patch

import pytest
from django.contrib.gis.geos import LineString, Point
from django.test import TestCase

# Mock external libraries before importing route_maker
with patch.dict(
    "sys.modules",
    {
        "googlemaps": Mock(),
        "mapbox": Mock(),
        "geopy.distance": Mock(),
        "shapely.geometry": Mock(),
        "shapely.ops": Mock(),
    },
):
    from helpers.route_maker import (
        Router,
        chunk_list,
        dic_to_ordered_list,
        line_length,
        pairs,
        unequal_point_pairs,
    )

pytestmark = pytest.mark.django_db


class TestUtilityFunctions(TestCase):
    """Tests for utility functions in route_maker"""

    def test_chunk_list_basic(self):
        """Test chunk_list with basic input"""
        test_list = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        chunks = list(chunk_list(test_list, 3))

        expected = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        self.assertEqual(chunks, expected)

    def test_chunk_list_uneven(self):
        """Test chunk_list with uneven division"""
        test_list = [1, 2, 3, 4, 5, 6, 7]
        chunks = list(chunk_list(test_list, 3))

        expected = [[1, 2, 3], [4, 5, 6], [7]]
        self.assertEqual(chunks, expected)

    def test_chunk_list_single_chunk(self):
        """Test chunk_list when chunk size is larger than list"""
        test_list = [1, 2, 3]
        chunks = list(chunk_list(test_list, 5))

        expected = [[1, 2, 3]]
        self.assertEqual(chunks, expected)

    def test_chunk_list_empty(self):
        """Test chunk_list with empty list"""
        chunks = list(chunk_list([], 3))
        self.assertEqual(chunks, [])

    @patch("helpers.route_maker.distance")
    @patch("helpers.route_maker.lonlat")
    @patch("helpers.route_maker.pairs")
    def test_line_length(self, mock_pairs, mock_lonlat, mock_distance):
        """Test line_length calculation"""
        # Mock a line with coordinates
        mock_line = Mock()
        mock_line.coords = [(-45.123, -23.456, 100), (-45.124, -23.457, 110)]

        # Mock pairs to return our coordinate pairs
        mock_pairs.return_value = [((-45.123, -23.456, 100), (-45.124, -23.457, 110))]

        # Mock lonlat to return mock objects
        mock_lonlat.return_value = Mock()

        # Mock distance calculation
        mock_distance_obj = Mock()
        mock_distance_obj.km = 0.5  # 500 meters
        mock_distance.return_value = mock_distance_obj

        result = line_length(mock_line)

        # Should calculate sqrt(distance² + elevation_diff²)
        # Expected: sqrt(0.5² + (0.01)²) = sqrt(0.25 + 0.0001) ≈ 0.5001
        self.assertAlmostEqual(result, 0.5001, places=3)

    def test_dic_to_ordered_list_basic(self):
        """Test dic_to_ordered_list with basic dictionary"""
        test_dict = {
            "3": {"name": "Third", "value": 30},
            "1": {"name": "First", "value": 10},
            "2": {"name": "Second", "value": 20},
        }

        result = dic_to_ordered_list(test_dict)

        expected = [
            {"name": "First", "value": 10, "key": 1},
            {"name": "Second", "value": 20, "key": 2},
            {"name": "Third", "value": 30, "key": 3},
        ]
        self.assertEqual(result, expected)

    def test_dic_to_ordered_list_empty(self):
        """Test dic_to_ordered_list with empty dictionary"""
        result = dic_to_ordered_list({})
        self.assertEqual(result, [])

    def test_pairs_basic(self):
        """Test pairs function with basic list"""
        test_list = [1, 2, 3, 4]
        result = list(pairs(test_list))

        expected = [(1, 2), (2, 3), (3, 4)]
        self.assertEqual(result, expected)

    def test_pairs_two_elements(self):
        """Test pairs with only two elements"""
        test_list = [1, 2]
        result = list(pairs(test_list))

        expected = [(1, 2)]
        self.assertEqual(result, expected)

    def test_pairs_single_element(self):
        """Test pairs with single element - should return empty"""
        test_list = [1]
        result = list(pairs(test_list))

        self.assertEqual(result, [])

    def test_unequal_point_pairs_with_duplicates(self):
        """Test unequal_point_pairs removing duplicates"""
        test_list = [1, 1, 2, 3, 3, 4]
        result = list(unequal_point_pairs(test_list))

        expected = [(1, 2), (2, 3), (3, 4)]
        self.assertEqual(result, expected)

    def test_unequal_point_pairs_no_duplicates(self):
        """Test unequal_point_pairs with no duplicates"""
        test_list = [1, 2, 3, 4]
        result = list(unequal_point_pairs(test_list))

        expected = [(1, 2), (2, 3), (3, 4)]
        self.assertEqual(result, expected)

    def test_unequal_point_pairs_all_same(self):
        """Test unequal_point_pairs with all same elements"""
        test_list = [1, 1, 1, 1]
        result = list(unequal_point_pairs(test_list))

        self.assertEqual(result, [])


class TestRouter(TestCase):
    """Tests for the Router class"""

    @patch("helpers.route_maker.googlemaps.Client")
    @patch("helpers.route_maker.Directions")
    def setUp(self, mock_directions, mock_gmaps_client):
        """Set up Router instance for testing"""
        self.mock_gmaps = Mock()
        self.mock_mapbox = Mock()

        mock_gmaps_client.return_value = self.mock_gmaps
        mock_directions.return_value = self.mock_mapbox

        self.router = Router("test_gmaps_key", "test_mapbox_key", False)
        self.manual_router = Router("test_gmaps_key", "test_mapbox_key", True)

    def test_router_initialization(self):
        """Test Router initialization"""
        self.assertIsNotNone(self.router.GoogleMaps)
        self.assertIsNotNone(self.router.MapBoxRoadMaps)
        self.assertFalse(self.router.manual_road)
        self.assertTrue(self.manual_router.manual_road)

        # Check initial state
        self.assertIsNone(self.router.marks)
        self.assertIsNone(self.router.dict_mark)
        self.assertIsNone(self.router.path)
        self.assertIsNone(self.router.length)

    @patch("helpers.route_maker.dic_to_ordered_list")
    def test_set_marks(self, mock_dic_to_ordered):
        """Test set_marks method"""
        test_marks = {
            "1": {"point": {"coordinates": [-45.1, -23.1]}, "name": "Mark 1"},
            "2": {"point": {"coordinates": [-45.2, -23.2]}, "name": "Mark 2"},
        }

        mock_ordered_list = [
            {"point": {"coordinates": [-45.1, -23.1]}, "name": "Mark 1", "key": 1},
            {"point": {"coordinates": [-45.2, -23.2]}, "name": "Mark 2", "key": 2},
        ]
        mock_dic_to_ordered.return_value = mock_ordered_list

        self.router.set_marks(test_marks)

        self.assertEqual(self.router.dict_mark, test_marks)
        self.assertEqual(self.router.marks, mock_ordered_list)
        mock_dic_to_ordered.assert_called_once_with(test_marks)

    @patch("helpers.route_maker.SHPoint")
    @patch("helpers.route_maker.SHMultiPoint")
    @patch("helpers.route_maker.nearest_points")
    @patch("helpers.route_maker.json.loads")
    def test_get_raw_route_points_automated_road(
        self, mock_json_loads, mock_nearest_points, mock_multipoint, mock_shpoint
    ):
        """Test get_raw_route_points with automated road (MapBox API)"""
        # Setup test marks
        self.router.marks = [
            {"point": {"coordinates": [-45.1, -23.1]}, "mapbox_call": True},
            {"point": {"coordinates": [-45.2, -23.2]}, "mapbox_call": True},
        ]
        self.router.dict_mark = {
            "1": {"point": {"coordinates": [-45.1, -23.1]}},
            "2": {"point": {"coordinates": [-45.2, -23.2]}},
        }

        # Mock MapBox response
        mock_response = Mock()
        mock_response.content = '{"routes": [{"geometry": {"coordinates": [[-45.15, -23.15], [-45.17, -23.17]]}}]}'
        self.mock_mapbox.directions.return_value = mock_response

        mock_json_loads.return_value = {
            "routes": [
                {"geometry": {"coordinates": [[-45.15, -23.15], [-45.17, -23.17]]}}
            ]
        }

        # Mock Shapely points - usando return_value ao invés de side_effect
        mock_point = Mock()
        mock_point.coords.xy = [["-45.0"], ["-23.0"]]
        mock_shpoint.return_value = mock_point

        # Mock nearest_points to return the same point
        mock_nearest_points.return_value = [mock_point]

        # Mock MultiPoint collection with proper __len__ method
        mock_collection = Mock()
        mock_collection.__len__ = Mock(
            side_effect=[3, 2, 1]
        )  # Decrease length each time
        mock_collection.geoms = [mock_point, mock_point]
        mock_multipoint.return_value = mock_collection

        result = self.router.get_raw_route_points()

        # Verify MapBox API was called
        self.mock_mapbox.directions.assert_called_once()

        # Verify result contains coordinates
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    @patch("helpers.route_maker.SHPoint")
    @patch("helpers.route_maker.SHLineString")
    @patch("helpers.route_maker.SHMultiPoint")
    @patch("helpers.route_maker.nearest_points")
    def test_get_raw_route_points_manual_road(
        self, mock_nearest_points, mock_multipoint, mock_linestring, mock_shpoint
    ):
        """Test get_raw_route_points with manual road"""
        # Setup manual router with marks
        self.manual_router.marks = [
            {"point": {"coordinates": [-45.1, -23.1]}},
            {"point": {"coordinates": [-45.2, -23.2]}},
        ]
        self.manual_router.dict_mark = {
            "1": {"point": {"coordinates": [-45.1, -23.1]}},
            "2": {"point": {"coordinates": [-45.2, -23.2]}},
        }

        # Mock Shapely points
        mock_point = Mock()
        mock_point.coords.xy = [["-45.0"], ["-23.0"]]
        mock_shpoint.return_value = mock_point

        # Mock collections with proper __len__ method
        mock_collection = Mock()
        mock_collection.__len__ = Mock(side_effect=[2, 1])  # Decrease length
        mock_collection.geoms = [mock_point]
        mock_multipoint.return_value = mock_collection

        # Mock nearest_points
        mock_nearest_points.return_value = [mock_point]

        result = self.manual_router.get_raw_route_points()

        # Verify MapBox API was NOT called
        self.mock_mapbox.directions.assert_not_called()

        # Verify result
        self.assertIsInstance(result, list)

    @patch("helpers.route_maker.chunk_list")
    def test_get_points_with_elevation(self, mock_chunk_list):
        """Test get_points_with_elevation method"""
        test_points = [[-45.1, -23.1], [-45.2, -23.2], [-45.3, -23.3]]

        # Mock chunk_list to return single chunk
        mock_chunk_list.return_value = [test_points]

        # Mock GoogleMaps elevation response
        elevation_response = [
            {"location": {"lng": -45.1, "lat": -23.1}, "elevation": 100},
            {"location": {"lng": -45.2, "lat": -23.2}, "elevation": 110},
            {"location": {"lng": -45.3, "lat": -23.3}, "elevation": 120},
        ]
        self.mock_gmaps.elevation.return_value = elevation_response

        result = self.router.get_points_with_elevation(test_points)

        # Verify GoogleMaps API was called
        self.mock_gmaps.elevation.assert_called_once_with(test_points)

        # Verify result contains Point objects
        self.assertEqual(len(result), 3)
        for point in result:
            self.assertIsInstance(point, Point)

    @patch("helpers.route_maker.line_length")
    def test_make_route_success(self, mock_line_length):
        """Test successful make_route execution"""
        # Mock the route creation process
        mock_line_length.return_value = 1500.0  # 1.5 km

        # Mock get_raw_route_points
        with patch.object(self.router, "get_raw_route_points") as mock_get_raw:
            mock_get_raw.return_value = [[-45.1, -23.1], [-45.2, -23.2]]

            # Mock get_points_with_elevation
            with patch.object(
                self.router, "get_points_with_elevation"
            ) as mock_get_elevation:
                mock_points = [
                    Point(-45.1, -23.1, 100, srid=4326),
                    Point(-45.2, -23.2, 110, srid=4326),
                ]
                mock_get_elevation.return_value = mock_points

                result = self.router.make_route()

                # Verify success
                self.assertTrue(result)
                self.assertIsInstance(self.router.path, LineString)
                self.assertEqual(self.router.path.srid, 4326)
                self.assertEqual(self.router.length, 1500.0)

    def test_make_route_exception_handling(self):
        """Test make_route exception handling"""
        # Mock get_raw_route_points to raise exception
        with patch.object(self.router, "get_raw_route_points") as mock_get_raw:
            mock_get_raw.side_effect = Exception("Test exception")

            result = self.router.make_route()

            # Verify failure
            self.assertFalse(result)

    def test_get_raw_route_points_no_mapbox_calls(self):
        """Test get_raw_route_points when no marks have mapbox_call flag"""
        # Setup marks without mapbox_call flag
        self.router.marks = [
            {"point": {"coordinates": [-45.1, -23.1]}},
            {"point": {"coordinates": [-45.2, -23.2]}},
        ]
        self.router.dict_mark = {
            "1": {"point": {"coordinates": [-45.1, -23.1]}},
            "2": {"point": {"coordinates": [-45.2, -23.2]}},
        }

        with patch("helpers.route_maker.SHPoint") as mock_shpoint, patch(
            "helpers.route_maker.SHMultiPoint"
        ) as mock_multipoint, patch(
            "helpers.route_maker.nearest_points"
        ) as mock_nearest_points, patch(
            "helpers.route_maker.json.loads"
        ) as mock_json_loads:

            # Mock MapBox response
            mock_response = Mock()
            mock_response.content = (
                '{"routes": [{"geometry": {"coordinates": [[-45.15, -23.15]]}}]}'
            )
            self.mock_mapbox.directions.return_value = mock_response

            mock_json_loads.return_value = {
                "routes": [{"geometry": {"coordinates": [[-45.15, -23.15]]}}]
            }

            # Mock Shapely points
            mock_point = Mock()
            mock_point.coords.xy = [["-45.0"], ["-23.0"]]
            mock_shpoint.return_value = mock_point

            # Mock nearest_points
            mock_nearest_points.return_value = [mock_point]

            # Mock MultiPoint collection with proper __len__ method
            mock_collection = Mock()
            mock_collection.__len__ = Mock(side_effect=[3, 2, 1])  # Decrease length
            mock_collection.geoms = [mock_point, mock_point]
            mock_multipoint.return_value = mock_collection

            self.router.get_raw_route_points()

            # Verify MapBox was called with first and last point
            expected_route = [
                {"coordinates": [-45.1, -23.1]},
                {"coordinates": [-45.2, -23.2]},
            ]
            self.mock_mapbox.directions.assert_called_once_with(
                expected_route, "mapbox/driving", geometries="geojson", overview="full"
            )
