from django.contrib.gis.db import models
from django.db.models import JSONField
from simple_history.models import HistoricalRecords

from apps.companies.models import Company


class Road(models.Model):
    DIRECTIONS = (
        (0, "Norte"),
        (1, "Sul"),
        (2, "Leste"),
        (3, "Oeste"),
        (4, "Ambos"),
        (5, "Não se aplica"),
    )

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=200, blank=True, null=True)
    direction = models.IntegerField(blank=True, choices=DIRECTIONS)
    marks = JSONField()
    uf = models.CharField(max_length=50, blank=True)
    company = models.ManyToManyField(Company, related_name="company_roads")

    path = models.LineStringField(blank=True, null=True, dim=3)
    length = models.FloatField(blank=True, null=True)

    metadata = JSONField(default=dict, blank=True, null=True)
    lot_logic = JSONField(default=dict, blank=True, null=True)
    city_logic = JSONField(default=dict, blank=True, null=True)
    lane_type_logic = JSONField(default=dict, blank=True, null=True)
    manual_road = models.BooleanField(default=False)
    is_default_segment = models.BooleanField(default=False)
    all_marks_have_indexes = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        return "{}: {}".format(self.id, self.name)

    @property
    def get_company_id(self):
        return self.company.first().uuid
