from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from helpers.filters import UUIDListFilter
from helpers.mixins import ListCacheMixin

from .models import City, Location, River
from .permissions import LocationPermissions, RiverPermissions
from .serializers import CitySerializer, LocationSerializer, RiverSerializer


class CityFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    service_order = UUIDListFilter(field_name="city_service_orders__uuid")

    class Meta:
        model = City
        fields = {"name": ["exact"]}


class CityViewSet(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = CitySerializer
    queryset = City.objects.all()
    permission_classes = [IsAuthenticated]
    filterset_class = CityFilter
    permissions = None
    ordering = "uuid"


class LocationFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    service_order = UUIDListFilter(field_name="location_service_orders__uuid")

    class Meta:
        model = Location
        fields = {"company": ["exact"]}


class LocationViewSet(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticated, LocationPermissions]
    filterset_class = LocationFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = Location.objects.none()

        user_companies = self.request.user.companies.all()
        queryset = Location.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset)


class RiverFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    service_order = UUIDListFilter(field_name="river_service_orders__uuid")

    class Meta:
        model = River
        fields = {
            "company": ["exact"],
            "locations": ["exact"],
            "locations__city": ["exact"],
        }


class RiverViewSet(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = RiverSerializer
    permission_classes = [IsAuthenticated, RiverPermissions]
    filterset_class = RiverFilter
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = River.objects.none()

        user_companies = self.request.user.companies.all()
        queryset = River.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset)
