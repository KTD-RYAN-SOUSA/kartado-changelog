from django.test import TestCase

from helpers.nested_objects import reporting_rgetattr, rgetattr, rsetattr


class TestRgetattr(TestCase):
    """Tests for rgetattr function (recursive getattr)"""

    def test_rgetattr_simple_attribute(self):
        """Test getting a simple attribute"""

        class SimpleObj:
            name = "test"

        obj = SimpleObj()
        result = rgetattr(obj, "name")
        assert result == "test"

    def test_rgetattr_nested_attribute(self):
        """Test getting nested attributes with dot notation"""

        class Inner:
            value = 42

        class Outer:
            inner = Inner()

        obj = Outer()
        result = rgetattr(obj, "inner.value")
        assert result == 42

    def test_rgetattr_deeply_nested(self):
        """Test getting deeply nested attributes"""

        class Level3:
            data = "deep"

        class Level2:
            level3 = Level3()

        class Level1:
            level2 = Level2()

        obj = Level1()
        result = rgetattr(obj, "level2.level3.data")
        assert result == "deep"

    def test_rgetattr_attribute_error(self):
        """Test that AttributeError is raised for non-existent attribute"""

        class SimpleObj:
            name = "test"

        obj = SimpleObj()
        with self.assertRaises(AttributeError):
            rgetattr(obj, "nonexistent")

    def test_rgetattr_nested_attribute_error(self):
        """Test AttributeError on nested non-existent attribute"""

        class Inner:
            value = 42

        class Outer:
            inner = Inner()

        obj = Outer()
        with self.assertRaises(AttributeError):
            rgetattr(obj, "inner.nonexistent")


class TestRsetattr(TestCase):
    """Tests for rsetattr function (recursive setattr)"""

    def test_rsetattr_simple_attribute(self):
        """Test setting a simple attribute"""

        class SimpleObj:
            name = "old"

        obj = SimpleObj()
        rsetattr(obj, "name", "new")
        assert obj.name == "new"

    def test_rsetattr_nested_attribute(self):
        """Test setting nested attributes with dot notation"""

        class Inner:
            value = 0

        class Outer:
            inner = Inner()

        obj = Outer()
        rsetattr(obj, "inner.value", 100)
        assert obj.inner.value == 100

    def test_rsetattr_deeply_nested(self):
        """Test setting deeply nested attributes"""

        class Level3:
            data = "old"

        class Level2:
            level3 = Level3()

        class Level1:
            level2 = Level2()

        obj = Level1()
        rsetattr(obj, "level2.level3.data", "new")
        assert obj.level2.level3.data == "new"

    def test_rsetattr_creates_new_attribute(self):
        """Test that rsetattr can create new attributes on simple objects"""

        class SimpleObj:
            pass

        obj = SimpleObj()
        rsetattr(obj, "new_attr", "value")
        assert obj.new_attr == "value"

    def test_rsetattr_attribute_error(self):
        """Test AttributeError when intermediate object doesn't exist"""

        class SimpleObj:
            pass

        obj = SimpleObj()
        with self.assertRaises(AttributeError):
            rsetattr(obj, "nonexistent.value", "fail")


class TestReportingRgetattr(TestCase):
    """Tests for reporting_rgetattr function (with __isnull handling)"""

    def test_reporting_rgetattr_simple_attribute(self):
        """Test getting a simple attribute"""

        class SimpleObj:
            name = "test"

        obj = SimpleObj()
        result = reporting_rgetattr(obj, "name")
        assert result == "test"

    def test_reporting_rgetattr_isnull_with_none_value(self):
        """Test __isnull suffix returns True when attribute is None"""

        class SimpleObj:
            value = None

        obj = SimpleObj()
        result = reporting_rgetattr(obj, "value__isnull")
        assert result is True

    def test_reporting_rgetattr_isnull_with_value(self):
        """Test __isnull suffix returns False when attribute has value"""

        class SimpleObj:
            value = 42

        obj = SimpleObj()
        result = reporting_rgetattr(obj, "value__isnull")
        assert result is False

    def test_reporting_rgetattr_isnull_with_empty_string(self):
        """Test __isnull with empty string (falsy but not None)"""

        class SimpleObj:
            value = ""

        obj = SimpleObj()
        result = reporting_rgetattr(obj, "value__isnull")
        assert result is True  # Empty string is falsy

    def test_reporting_rgetattr_isnull_with_zero(self):
        """Test __isnull with zero (falsy but not None)"""

        class SimpleObj:
            value = 0

        obj = SimpleObj()
        result = reporting_rgetattr(obj, "value__isnull")
        assert result is True  # 0 is falsy

    def test_reporting_rgetattr_nested_attribute(self):
        """Test getting nested attributes"""

        class Inner:
            value = 100

        class Outer:
            inner = Inner()

        obj = Outer()
        result = reporting_rgetattr(obj, "inner.value")
        assert result == 100

    def test_reporting_rgetattr_nested_with_isnull(self):
        """Test nested attribute with __isnull suffix"""

        class Inner:
            value = None

        class Outer:
            inner = Inner()

        obj = Outer()
        with self.assertRaises(AttributeError):
            reporting_rgetattr(obj, "value__isnull")
        with self.assertRaises(AttributeError):
            reporting_rgetattr(obj, "inner.value__isnull")
