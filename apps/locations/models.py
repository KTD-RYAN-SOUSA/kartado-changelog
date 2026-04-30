import uuid

from django.contrib.gis.db import models
from simple_history.models import HistoricalRecords

from apps.companies.models import Company


class City(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uf_code = models.IntegerField()
    name = models.TextField()
    coordinates = models.PointField(blank=True, null=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] {}".format(self.uf_code, self.name)


class Location(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True)
    name = models.TextField()
    coordinates = models.PointField(blank=True, null=True)

    history = HistoricalRecords()

    def __str__(self):
        return "[{}]- [{}] {}".format(
            self.company.name if self.company else "NO-COMPANY",
            self.city.name if self.city else "NO-CITY",
            self.name,
        )

    @property
    def get_company_id(self):
        return self.company_id


class River(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.TextField()
    locations = models.ManyToManyField(
        Location, related_name="rivers_in_location", blank=True
    )

    history = HistoricalRecords()

    def __str__(self):
        return "[{}] - {}".format(
            self.company.name if self.company else "NO-COMPANY", self.name
        )

    @property
    def get_company_id(self):
        return self.company_id
