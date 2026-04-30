from django.test import TestCase

from helpers.arrays import is_matrix


class TestIsMatrix(TestCase):
    """Tests for the is_matrix function"""

    def test_is_matrix_valid_list_of_lists(self):
        """Test that a valid matrix (list of lists) returns True"""
        matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        assert is_matrix(matrix) is True

    def test_is_matrix_valid_list_of_tuples(self):
        """Test that a list of tuples with same length returns True"""
        matrix = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]
        assert is_matrix(matrix) is True

    def test_is_matrix_valid_list_of_sets(self):
        """Test that a list of sets with same length returns True"""
        matrix = [{1, 2, 3}, {4, 5, 6}, {7, 8, 9}]
        assert is_matrix(matrix) is True

    def test_is_matrix_mixed_row_types(self):
        """Test that a list with mixed row types (list, tuple, set) returns True if same length"""
        matrix = [[1, 2, 3], (4, 5, 6), {7, 8, 9}]
        assert is_matrix(matrix) is True

    def test_is_matrix_single_row(self):
        """Test that a single row matrix returns True"""
        matrix = [[1, 2, 3]]
        assert is_matrix(matrix) is True

    def test_is_matrix_single_column(self):
        """Test that a single column matrix returns True"""
        matrix = [[1], [2], [3]]
        assert is_matrix(matrix) is True

    def test_is_matrix_not_a_list(self):
        """Test that non-list input returns False"""
        assert is_matrix("not a matrix") is False
        assert is_matrix(123) is False
        assert is_matrix(None) is False
        assert is_matrix({1, 2, 3}) is False

    def test_is_matrix_list_with_non_iterable_elements(self):
        """Test that a list with non-iterable elements returns False"""
        matrix = [1, 2, 3]
        assert is_matrix(matrix) is False

    def test_is_matrix_list_with_mixed_elements(self):
        """Test that a list with mixed iterable and non-iterable elements returns False"""
        matrix = [[1, 2, 3], 4, [5, 6, 7]]
        assert is_matrix(matrix) is False

    def test_is_matrix_empty_list(self):
        """Test that an empty list returns False"""
        matrix = []
        assert is_matrix(matrix) is False

    def test_is_matrix_different_row_lengths(self):
        """Test that rows with different lengths return False"""
        matrix = [[1, 2, 3], [4, 5], [6, 7, 8]]
        assert is_matrix(matrix) is False

    def test_is_matrix_rows_with_different_lengths_at_end(self):
        """Test that inconsistent row lengths return False"""
        matrix = [[1, 2], [3, 4], [5, 6, 7]]
        assert is_matrix(matrix) is False

    def test_is_matrix_with_empty_rows(self):
        """Test that a matrix with empty rows returns True if all rows are empty"""
        matrix = [[], [], []]
        assert is_matrix(matrix) is True

    def test_is_matrix_with_one_empty_row(self):
        """Test that a matrix with one empty row among non-empty rows returns False"""
        matrix = [[1, 2], [], [3, 4]]
        assert is_matrix(matrix) is False

    def test_is_matrix_nested_lists(self):
        """Test that nested lists (3D matrix) with consistent dimensions return True"""
        matrix = [[[1, 2]], [[3, 4]], [[5, 6]]]
        assert is_matrix(matrix) is True

    def test_is_matrix_strings_as_rows(self):
        """Test that strings as rows (iterable) return True if same length"""
        matrix = ["abc", "def", "ghi"]
        # Strings are iterables but not lists/tuples/sets, so should return False
        assert is_matrix(matrix) is False

    def test_is_matrix_strings_different_lengths(self):
        """Test that strings with different lengths return False"""
        matrix = ["abc", "de", "fgh"]
        assert is_matrix(matrix) is False
