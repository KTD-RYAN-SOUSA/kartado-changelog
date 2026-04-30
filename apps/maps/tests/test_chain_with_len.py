import pytest

from apps.maps.views import ChainWithLen
from apps.reportings.models import Reporting

pytestmark = pytest.mark.django_db


class TestChainWithLen:
    """Test suite for ChainWithLen class."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing."""
        # Regular lists
        list1 = [1, 2, 3]
        list2 = [4, 5, 6]

        # Django querysets
        queryset1 = Reporting.objects.all()

        return {
            "lists": [list1, list2],
            "querysets": [queryset1],
            "mixed": [list1, queryset1],
            "reportings": queryset1,
        }

    def test_init(self, sample_data):
        """Test initialization with different types of iterables."""
        # Test with lists
        chain = ChainWithLen(*sample_data["lists"])
        assert list(chain.querysets) == sample_data["lists"]
        assert list(chain) == [1, 2, 3, 4, 5, 6]

        # Test with querysets
        chain = ChainWithLen(*sample_data["querysets"])
        assert list(chain.querysets) == sample_data["querysets"]

        # Test with mixed types
        chain = ChainWithLen(*sample_data["mixed"])
        assert list(chain.querysets) == sample_data["mixed"]

    def test_len(self, sample_data):
        """Test length calculation."""

        chain = ChainWithLen(*sample_data["querysets"])
        assert len(chain) == 5

    def test_getitem_slice(self, sample_data):
        """Test slicing functionality."""
        chain = ChainWithLen(*sample_data["querysets"])

        # Test various slices
        assert chain[1:3] == list(sample_data["reportings"][1:3])
        assert chain[:3] == list(sample_data["reportings"][:3])
        assert chain[3:] == list(sample_data["reportings"][3:])

    def test_getitem_index(self, sample_data):
        """Test individual index access."""
        chain = ChainWithLen(*sample_data["querysets"])

        assert chain[0] == sample_data["reportings"][0]
        assert chain[3] == sample_data["reportings"][3]

        with pytest.raises(IndexError):
            chain[10]

    def test_lazy_length_calculation(self, sample_data):
        """Test that length is calculated lazily."""
        chain = ChainWithLen(*sample_data["querysets"])
        assert chain._len is None

        # Access length
        _ = len(chain)
        assert chain._len == 5

    @pytest.mark.django_db
    def test_with_django_querysets(self, sample_data):
        """Test with Django querysets."""
        queryset = sample_data["reportings"]

        # Create chain with querysets
        chain = ChainWithLen(queryset)

        # Test length
        assert len(chain) == queryset.count()

        # Test iteration
        items = list(chain)
        assert len(items) == queryset.count()
        assert isinstance(items[0], Reporting)
