import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon

from apps.companies.models import Company
from apps.companies.serializers import CompanySerializer

pytestmark = pytest.mark.django_db


def test_get_bounding_box_with_shape():
    polygon = Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)))
    multipolygon = MultiPolygon(polygon)
    company = Company.objects.create(name="BBox Test", shape=multipolygon)

    serializer = CompanySerializer()
    result = serializer.get_bounding_box(company)

    assert isinstance(result, list)
    assert len(result) == 4
    assert result == list(multipolygon.extent)


def test_get_bounding_box_without_shape():
    company = Company.objects.create(name="BBox Empty", shape=None)

    serializer = CompanySerializer()
    result = serializer.get_bounding_box(company)

    assert result == []
