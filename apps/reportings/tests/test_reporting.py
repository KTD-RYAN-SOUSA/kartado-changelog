import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
import pytz
from django.contrib.gis.geos import GeometryCollection, Point
from django.utils import timezone
from requests.models import Response
from rest_framework import status

from apps.companies.models import Firm, SubCompany
from apps.maps.models import ShapeFile
from apps.occurrence_records.models import OccurrenceType, RecordPanel
from apps.reportings.models import RecordMenu, Reporting, ReportingRelation
from apps.roads.models import Road
from apps.service_orders.models import (
    ServiceOrderActionStatus,
    ServiceOrderActionStatusSpecs,
)
from apps.services.models import Service
from apps.users.models import User
from apps.work_plans.models import Job
from helpers.signals import DisableSignals
from helpers.strings import get_obj_from_path, to_snake_case
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestReporting(TestBase):
    model = "Reporting"

    def test_list_reporting(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 4

    def test_filter_reporting(self, client):
        obj = Reporting.objects.filter(
            company=self.company,
            reporting_usage__isnull=False,
            reporting_usage__measurement__isnull=False,
        ).exclude(occurrence_type__occurrence_kind="2")[0]
        measurement = obj.reporting_usage.filter(measurement__isnull=False)[
            0
        ].measurement

        response = client.get(
            path="/{}/?company={}&num_jobs={}&measurement={}&page_size=1".format(
                self.model, str(self.company.pk), str(2), str(measurement.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_reporting_without_queryset(self, client):
        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        false_permission(self.user, self.company, self.model, allowed="self")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_reporting_without_company(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_reporting(self, client):
        self.company.metadata["use_direction"] = True
        self.company.save()

        obj = Reporting.objects.filter(company=self.company).exclude(
            occurrence_type__occurrence_kind="2"
        )[0]

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_reporting_with_others_parameters(self, client):
        self.company.metadata["use_direction"] = False
        self.company.save()

        obj = Reporting.objects.filter(
            company=self.company,
            reporting_usage__isnull=False,
            reporting_usage__measurement__isnull=False,
        ).exclude(occurrence_type__occurrence_kind="2")[0]

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_reporting(self, client):
        job = Job.objects.filter(company=self.company).first()
        road = Road.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).first()
        occurrence_type = OccurrenceType.objects.filter(company=self.company).first()
        service_order_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()
        service = Service.objects.filter(
            company=self.company, occurrence_types=occurrence_type
        ).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "roadName": str(road.name),
                        "km": 0,
                        "direction": str(road.direction),
                        "lane": "1",
                        "formData": {"x": 100, "y": 1},
                        "track": "testTrack",
                        "branch": "testBranch",
                        "kmReference": 1.0,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type.pk),
                            }
                        },
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(service_order_status.pk),
                            }
                        },
                        "job": {"data": {"type": "Job", "id": str(job.pk)}},
                        "resources": {
                            "data": [
                                {
                                    "type": "Service",
                                    "id": str(service.pk),
                                    "amount": 123,
                                }
                            ]
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # attributes are filled correctly
        reporting_attr = content["data"]["attributes"]
        assert reporting_attr["track"] == "testTrack"
        assert reporting_attr["branch"] == "testBranch"
        assert reporting_attr["kmReference"] == 1.0

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_reporting_with_status(self, client):
        # TEST CREATE sending executed_at and status executed
        job = Job.objects.filter(company=self.company).first()
        road = Road.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).first()
        occurrence_type = OccurrenceType.objects.filter(company=self.company).first()
        service = Service.objects.filter(
            company=self.company, occurrence_types=occurrence_type
        ).first()

        executed_status_order = self.company.metadata["executed_status_order"]
        new_executed = timezone.now() - timedelta(days=1)

        status_specs = ServiceOrderActionStatusSpecs.objects.filter(
            company=self.company, order__gte=executed_status_order
        )[0]

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "roadName": str(road.name),
                        "km": 0,
                        "direction": str(road.direction),
                        "lane": "1",
                        "formData": {"x": 100, "y": 1},
                        "executedAt": new_executed,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type.pk),
                            }
                        },
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(status_specs.status.pk),
                            }
                        },
                        "job": {"data": {"type": "Job", "id": str(job.pk)}},
                        "resources": {
                            "data": [
                                {
                                    "type": "Service",
                                    "id": str(service.pk),
                                    "amount": 123,
                                }
                            ]
                        },
                    },
                }
            },
        )

        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])
        assert (
            obj_created.executed_at.astimezone(tz=None).replace(tzinfo=pytz.utc).date()
            == new_executed.astimezone(tz=None).replace(tzinfo=pytz.utc).date()
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # TEST CREATE not sending executed_at and status executed
        job = Job.objects.filter(company=self.company).first()
        road = Road.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).first()
        occurrence_type = OccurrenceType.objects.filter(company=self.company).first()
        service = Service.objects.filter(
            company=self.company, occurrence_types=occurrence_type
        ).first()

        executed_status_order = self.company.metadata["executed_status_order"]

        status_specs = ServiceOrderActionStatusSpecs.objects.filter(
            company=self.company, order__gte=executed_status_order
        )[0]

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "roadName": str(road.name),
                        "km": 0,
                        "direction": str(road.direction),
                        "lane": "1",
                        "formData": {"x": 100, "y": 1},
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type.pk),
                            }
                        },
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(status_specs.status.pk),
                            }
                        },
                        "job": {"data": {"type": "Job", "id": str(job.pk)}},
                        "resources": {
                            "data": [
                                {
                                    "type": "Service",
                                    "id": str(service.pk),
                                    "amount": 123,
                                }
                            ]
                        },
                    },
                }
            },
        )

        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])
        assert obj_created.executed_at.date() == timezone.now().date()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_reporting_with_autofill(self, client):
        road = Road.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).first()
        service_order_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()
        occurrence_type = None
        autofill_field = None
        for o_type in OccurrenceType.objects.filter(company=self.company):
            if any(["autofill" in a for a in o_type.form_fields["fields"]]):
                occurrence_type = o_type
                autofill_field = next(
                    a for a in o_type.form_fields["fields"] if "autofill" in a
                )

        assert occurrence_type is not None

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "roadName": str(road.name),
                        "km": 0,
                        "direction": str(road.direction),
                        "lane": "1",
                        "formData": {"x": 100, "y": 1},
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type.pk),
                            }
                        },
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(service_order_status.pk),
                            }
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        autofill_field_name = to_snake_case(autofill_field["apiName"])
        assert autofill_field_name in obj_created.form_data

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    # Try to create a Reporting object providing information about a non-existant
    # field in the formMetadata. It shouldn't crash
    def test_create_reporting_with_non_existant_form_metadata(self, client):
        road = Road.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).first()
        service_order_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()
        occurrence_type = OccurrenceType.objects.filter(company=self.company).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "roadName": str(road.name),
                        "km": 0,
                        "direction": str(road.direction),
                        "lane": "1",
                        "formData": {"x": 100, "y": 1},
                        "formMetadata": {"asdjnasdas": {"manuallySpecified": False}},
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type.pk),
                            }
                        },
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(service_order_status.pk),
                            }
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    # Create a Reporting object using an OccurrenceType with an autofill field
    # and then change the OccurrenceType to one that doens't have that field.
    # It should not crash.
    def test_create_reporting_and_change_occurrence_type(self, client):
        road = Road.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).first()
        service_order_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()
        occurrence_type_with_autofill = None
        occurrence_type_without_autofill = None
        autofill_field = None
        for o_type in OccurrenceType.objects.filter(company=self.company):
            if any(["autofill" in a for a in o_type.form_fields["fields"]]):
                occurrence_type_with_autofill = o_type
                autofill_field = next(
                    a for a in o_type.form_fields["fields"] if "autofill" in a
                )

        assert occurrence_type_with_autofill is not None

        for o_type in OccurrenceType.objects.filter(company=self.company):
            if not any(["autofill" in a for a in o_type.form_fields["fields"]]):
                occurrence_type_without_autofill = o_type

        assert occurrence_type_without_autofill is not None

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "roadName": str(road.name),
                        "km": 0,
                        "direction": str(road.direction),
                        "lane": "1",
                        "formData": {"x": 100, "y": 1},
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type_with_autofill.pk),
                            }
                        },
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(service_order_status.pk),
                            }
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        reporting = Reporting.objects.get(pk=content["data"]["id"])
        assert reporting.__str__()

        autofill_field_name = to_snake_case(autofill_field["apiName"])
        assert autofill_field_name in reporting.form_data

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {
                        "formData": {"x": 100, "y": 2},
                        "reason": "test",
                    },
                    "relationships": {
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type_without_autofill.pk),
                            }
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

    def test_delete_reporting(self, client):
        instance = (
            Reporting.objects.filter(company=self.company)
            .exclude(occurrence_type__occurrence_kind="2")
            .first()
        )

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_reporting_updates_job_reporting_count(self, client):
        instance = (
            Reporting.objects.filter(company=self.company, job__isnull=False)
            .exclude(occurrence_type__occurrence_kind="2")
            .first()
        )
        job = instance.job

        # Since fixture import doesn't trigger signals,
        # .save() guarantees it's properly calculated before testing
        job.save()

        orig_reporting_count = job.reporting_count

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        job.refresh_from_db()
        new_reporting_count = job.reporting_count

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # reporting_count has been subtracted
        assert new_reporting_count == orig_reporting_count - 1

    def test_update_reporting(self, client):
        # service = Service.objects.filter(company=self.company)[0]
        # occurrence_type = service.occurrence_types.filter(
        #     company__in=[self.company]
        # )[0]
        # reporting = Reporting.objects.filter(
        #     company=self.company, occurrence_type=occurrence_type
        # )[0]

        # services_usage = ServiceUsage.objects.filter(
        #     service=service, reporting=reporting
        # ).distinct()

        # old_current_balance = service.current_balance

        reporting = Reporting.objects.filter(company=self.company).exclude(
            occurrence_type__occurrence_kind="2"
        )[0]

        service = Service.objects.filter(
            company_id=reporting.company.pk,
            occurrence_types=reporting.occurrence_type,
        )[0]

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {
                        "formData": {"x": 100, "y": 2},
                        "reason": "test",
                    },
                    "relationships": {
                        "resources": {
                            "data": [
                                {
                                    "type": "Service",
                                    "id": str(service.pk),
                                    "amount": 123,
                                }
                            ]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

    def test_update_reporting_with_wrong_amount(self, client):
        reporting = Reporting.objects.filter(company=self.company).exclude(
            occurrence_type__occurrence_kind="2"
        )[0]

        service = Service.objects.filter(
            company_id=reporting.company.pk,
            occurrence_types=reporting.occurrence_type,
        )[0]

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {
                        "formData": {"x": 100, "y": 2},
                        "reason": "test",
                    },
                    "relationships": {
                        "resources": {
                            "data": [
                                {
                                    "type": "Service",
                                    "id": str(service.pk),
                                    "amount": "hh",
                                }
                            ]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_status_reporting(self, client):
        # TEST UPDATE sending executed_at and status executed
        executed_status_order = self.company.metadata["executed_status_order"]

        not_executed_status = ServiceOrderActionStatusSpecs.objects.filter(
            company=self.company, order__lt=executed_status_order
        ).values_list("status", flat=True)

        executed_status = ServiceOrderActionStatusSpecs.objects.filter(
            company=self.company, order__gte=executed_status_order
        ).values_list("status", flat=True)

        reporting = Reporting.objects.filter(
            company=self.company, status__in=executed_status
        ).exclude(occurrence_type__occurrence_kind="2")[0]

        executed_before = reporting.executed_at
        new_executed = (
            executed_before + timedelta(days=1)
            if executed_before
            else timezone.now() - timedelta(days=1)
        )

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {
                        "uuid": str(reporting.pk),
                        "executedAt": new_executed,
                    },
                    "relationships": {
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(executed_status[0]),
                            }
                        }
                    },
                }
            },
        )

        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])

        assert (
            obj_created.executed_at.astimezone(tz=None).replace(tzinfo=pytz.utc).date()
            == new_executed.astimezone(tz=None).replace(tzinfo=pytz.utc).date()
        )
        assert response.status_code == status.HTTP_200_OK

        # TEST UPDATE sending executed_at and status not executed
        reporting = Reporting.objects.filter(
            company=self.company, status__in=executed_status
        ).exclude(occurrence_type__occurrence_kind="2")[0]

        executed_before = reporting.executed_at
        new_executed = (
            executed_before + timedelta(days=1)
            if executed_before
            else timezone.now() - timedelta(days=1)
        )

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {
                        "uuid": str(reporting.pk),
                        "executedAt": new_executed,
                    },
                    "relationships": {
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(not_executed_status[0]),
                            }
                        }
                    },
                }
            },
        )

        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])

        assert obj_created.executed_at is None
        assert response.status_code == status.HTTP_200_OK

        # TEST UPDATE not sending executed_at and status executed
        reporting = Reporting.objects.filter(
            company=self.company,
            status__in=not_executed_status,
            executed_at__isnull=True,
        ).exclude(occurrence_type__occurrence_kind="2")[0]

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {"uuid": str(reporting.pk)},
                    "relationships": {
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(executed_status.first()),
                            }
                        }
                    },
                }
            },
        )

        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])

        assert obj_created.executed_at.date() == timezone.now().date()
        assert response.status_code == status.HTTP_200_OK

        # TEST UPDATE not sending executed_at and status not executed
        reporting = Reporting.objects.filter(
            company=self.company,
            status__in=executed_status,
            executed_at__isnull=False,
        ).exclude(occurrence_type__occurrence_kind="2")[0]

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {"uuid": str(reporting.pk)},
                    "relationships": {
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(not_executed_status.first()),
                            }
                        }
                    },
                }
            },
        )

        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])

        assert obj_created.executed_at is None
        assert response.status_code == status.HTTP_200_OK

    def test_bulk_reporting_wont_change_end_km(self, client):
        # Make sure that the bulk reporting edit endpoint will not change
        # an end_km when such information isn't included in the request

        obj = Reporting.objects.filter(
            company=self.company, end_km_manually_specified=True
        ).first()
        firm = Firm.objects.filter(company=self.company).exclude(pk=obj.firm.pk).first()

        original_end_km = obj.end_km

        response = client.post(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"direction": "1"},
                    "relationships": {
                        "reportings": {
                            "data": [{"type": self.model, "id": str(obj.pk)}]
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                    },
                }
            },
        )

        edited_reporting = Reporting.objects.get(uuid=obj.pk)

        assert response.status_code == status.HTTP_200_OK
        assert edited_reporting.end_km == original_end_km
        assert edited_reporting.end_km_manually_specified

        response = client.post(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"end_km": 100},
                    "relationships": {
                        "reportings": {
                            "data": [{"type": self.model, "id": str(obj.pk)}]
                        }
                    },
                }
            },
        )

        edited_reporting = Reporting.objects.get(uuid=obj.pk)

        assert response.status_code == status.HTTP_200_OK
        assert edited_reporting.end_km == 100
        assert edited_reporting.end_km_manually_specified

        response = client.post(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"end_km_manually_specified": False},
                    "relationships": {
                        "reportings": {
                            "data": [{"type": self.model, "id": str(obj.pk)}]
                        }
                    },
                }
            },
        )

        edited_reporting = Reporting.objects.get(uuid=obj.pk)

        assert response.status_code == status.HTTP_200_OK
        assert edited_reporting.end_km == edited_reporting.km
        assert not edited_reporting.end_km_manually_specified

    def test_bulk_reporting(self, client):
        obj = Reporting.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).exclude(pk=obj.firm.pk).first()

        response = client.post(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"direction": "1"},
                    "relationships": {
                        "reportings": {
                            "data": [{"type": self.model, "id": str(obj.pk)}]
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.post(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"km": 500.0},
                    "relationships": {
                        "reportings": {
                            "data": [{"type": self.model, "id": str(obj.pk)}]
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.post(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"direction": "1"},
                    "relationships": {
                        "reportings": {"data": [{}]},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # delete
        response = client.delete(
            path="/{}/{}/".format(self.model, "Bulk"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "reportings": {
                            "data": [{"type": self.model, "id": str(obj.pk)}]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

    # ------------------ TESTS with others ENDPOINTS --------------------

    def test_list_reporting_geo(self, client):
        self.company.metadata["use_direction"] = True
        self.company.save()

        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "ReportingGeo", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        self.company.metadata["use_direction"] = False
        self.company.save()

        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "ReportingGeo", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_reporting_geo_without_queryset(self, client):
        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "ReportingGeo", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        false_permission(self.user, self.company, self.model, allowed="self")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "ReportingGeo", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_reporting_geo(self, client):
        obj = Reporting.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                "ReportingGeo", str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_dashboard_reporting(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "DashboardReporting", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_dashboard_reporting_without_queryset(self, client):
        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "DashboardReporting", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        false_permission(self.user, self.company, self.model, allowed="self")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "DashboardReporting", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_dashboard_reporting(self, client):
        obj = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="1"
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                "DashboardReporting", str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_reporting_count(self, client):
        occurrence_type = OccurrenceType.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/?company={}&from_year={}&occurrence_type={}&page_size=1".format(
                "dashboard/ReportingCount",
                str(self.company.pk),
                "2020",
                str(occurrence_type.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&from_year={}&occurrence_type={}&period={}&page_size=1".format(
                "dashboard/ReportingCount",
                str(self.company.pk),
                "2020",
                str(occurrence_type.pk),
                "day",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&from_year={}".format(
                "dashboard/ReportingCount", str(self.company.pk), "2019"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_rain_data(self, client):
        response = client.get(
            path="/{}/?company={}&start_date={}&end_date={}".format(
                "dashboard/RainData",
                str(self.company.pk),
                "12/12/2019",
                "05/06/2020",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&start_date={}".format(
                "dashboard/RainData", str(self.company.pk), "12/12/2019"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.get(
            path="/{}/?company={}&start_date={}&end_date={}".format(
                "dashboard/RainData",
                str(self.company.pk),
                "12/12/2019",
                "05kkkk",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_reporting_count_road(self, client):
        occurrence_type = OccurrenceType.objects.filter(company=self.company).first()
        road = Road.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/?company={}&start_date={}&end_date={}&occurrence_type={}&km_step={}&road_name={}".format(
                "dashboard/ReportingCountRoad",
                str(self.company.pk),
                "12/12/2019",
                "05/06/2020",
                str(occurrence_type.pk),
                str(1000),
                str(road.name),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&start_date={}&end_date={}".format(
                "dashboard/ReportingCountRoad",
                str(self.company.pk),
                "12/12/2019",
                "05/06/2020",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.get(
            path="/{}/?company={}&start_date={}&end_date={}&occurrence_type={}&km_step={}&road_name={}".format(
                "dashboard/ReportingCountRoad",
                str(self.company.pk),
                "12/12/2019",
                "05ahah2020",
                str(occurrence_type.pk),
                str(1000),
                str(road.name),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.get(
            path="/{}/?company={}&start_date={}&end_date={}&occurrence_type={}&km_step={}&road_name={}".format(
                "dashboard/ReportingCountRoad",
                str(self.company.pk),
                "12/12/2019",
                "05/06/2020",
                str(occurrence_type.pk),
                str(100.4),
                str(road.name),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reporting_filter_accepts_partial_range(self, client):
        """
        Ensures the correct behavior when querying with the form_data
        filter. Also makes sure that partial ranges work properly.
        """

        # Update the reporting used for tests to have formData of "length" with value 10
        reporting = Reporting.objects.filter(company=self.company).exclude(
            occurrence_type__occurrence_kind="2"
        )[0]

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {"formData": {"length": 10}},
                }
            },
        )

        # Ensure the update went okay
        assert response.status_code == status.HTTP_200_OK

        def api_call_with_range(range):
            """
            Calls the Reporting endpoint with the provided form_data
            and returns the response data.
            """
            response = client.get(
                path="/{}/?company={}&form_data={}".format(
                    self.model, str(self.company.pk), range
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
                data={},
            )
            return response.data

        # From length 10 to 100 (inclusive)
        resp = api_call_with_range('{"length":{"from":10,"to":100}}')
        # Check it's one result
        assert resp["meta"]["pagination"]["count"] == 1
        # Ensure its length is the provided one
        assert resp["results"][0]["form_data"]["length"] == 10

        # Partial range from 10
        # Check the same result still appears with a partial "from" range
        resp = api_call_with_range('{"length":{"from":10}}')
        assert resp["meta"]["pagination"]["count"] == 1

        # Partial range to 100
        # Check the same result still appears with a partial "to" range
        resp = api_call_with_range('{"length":{"to":100}}')
        assert resp["meta"]["pagination"]["count"] == 1

    @pytest.mark.parametrize(
        "param",
        [
            "address=Rodovia+SC+401+ km+4+Saco+Grande",
            "latlng=-27.5449033,-48.500166",
            "place_id=ChIJrRG4Plw4J5URpljPp8zfUX4",
        ],
    )
    @pytest.mark.geocoding
    def test_reporting_geocoding(self, client, param):
        response = client.get(
            path="/Reporting/Geocoding/?company={}&{}".format(
                str(self.company.pk), param
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.geocoding
    def test_reporting_geocoding_error(self, client):
        response = client.get(
            path="/Reporting/Geocoding/?company={}".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reporting_recordpanel_filter(self, client):

        reporting_instance = Reporting.objects.filter(menu__isnull=False).first()

        record_panel_instance = RecordPanel.objects.filter(
            menu=reporting_instance.menu
        ).first()

        response = client.get(
            path="/{}/?company={}&record_panel={}".format(
                self.model, str(self.company.pk), str(record_panel_instance.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        assert str(reporting_instance.pk) in [item["id"] for item in content["data"]]
        assert response.status_code == status.HTTP_200_OK

    def test_shared_with_agency_is_handled_in_endpoint(self, client):
        """
        Ensure shared_with_agency is handled in the endpoint
        """

        reporting = Reporting.objects.filter(
            company=self.company, shared_with_agency=True
        ).first()

        response = client.get(
            path="/Reporting/{}/?company={}".format(
                str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["data"]["attributes"]["sharedWithAgency"]

        response = client.get(
            path="/Reporting/?company={}&shared_with_agency=true".format(
                str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

        response = client.get(
            path="/Reporting/?company={}&shared_with_agency=false".format(
                str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 3

    def test_antt_supervisor_agency_qs_permissions(self, client):
        """
        Ensure antt_supervisor_agency queryset permission properly limits the results
        """

        false_permission(
            self.user, self.company, self.model, allowed="antt_supervisor_agency"
        )

        response = client.get(
            path="/Reporting/?company={}".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_is_shared_with_agency_endpoint(self, client):
        """
        Ensure the IsSharedWithAgency endpoint is working correctly
        """

        reporting = Reporting.objects.filter(
            company=self.company, shared_with_agency=True
        ).first()

        response = client.get(
            path="/Reporting/{}/IsSharedWithAgency/?company={}".format(
                str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["data"]["isSharedWithAgency"]

    def request_with_classification_filter(self, client, filter_name):
        response = client.get(
            path="/{}/?company={}&page_size=1&{}=1".format(
                self.model, str(self.company.pk), filter_name
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_hole_classification_filter(self, client):
        self.request_with_classification_filter(client, "reporting_hole_classification")

    def test_sheet_classification_filter(self, client):
        self.request_with_classification_filter(
            client, "reporting_sheet_classification"
        )

    def test_reporting_create_and_delete_self_relations(self, client):
        reporting = Reporting.objects.filter(company=self.company).exclude(
            occurrence_type__occurrence_kind="2"
        )[0]
        reporting_relation = ReportingRelation.objects.filter(company=self.company)
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {
                        "createSelfRelations": [
                            {
                                "parent": str(reporting.pk),
                                "child": "00015140-5cf4-43b9-be76-fa2e21da0b1c",
                                "reportingRelation": str(reporting_relation[0].pk),
                            },
                            {
                                "parent": "00000db3-a561-4387-ac47-d48fca2d6c24",
                                "child": str(reporting.pk),
                                "reportingRelation": str(reporting_relation[1].pk),
                            },
                        ],
                        "deleteSelfRelations": [
                            {"uuid": "ab8076db-7590-4e6c-83fa-a724e2d7133d"}
                        ],
                    },
                }
            },
        )
        assert response.status_code == status.HTTP_200_OK

    def test_reporting_create_self_relations_post_error(self, client):
        road = Road.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).first()
        occurrence_type = OccurrenceType.objects.filter(company=self.company).first()
        service_order_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()
        reporting_relation = ReportingRelation.objects.filter(company=self.company)

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "roadName": str(road.name),
                        "km": 0,
                        "direction": str(road.direction),
                        "lane": "1",
                        "formData": {"x": 100, "y": 1},
                        "track": "testTrack",
                        "branch": "testBranch",
                        "kmReference": 1.0,
                        "createSelfRelations": [
                            {
                                "parent": None,
                                "child": None,
                                "reportingRelation": str(reporting_relation[0].pk),
                            },
                            {
                                "parent": "00000db3-a561-4387-ac47-d48fca2d6c24",
                                "child": "00015140-5cf4-43b9-be76-fa2e21da0b1c",
                                "reportingRelation": str(reporting_relation[1].pk),
                            },
                        ],
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type.pk),
                            }
                        },
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(service_order_status.pk),
                            }
                        },
                    },
                }
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        content = json.loads(response.content)
        expected_message = "kartado.error.reporting_in_reporting.invalid_link"
        assert content["errors"][0]["detail"] == expected_message

    def test_reportings_from_inspection(self, client):
        new_form_data = {
            "therapy": [
                {"occurrence_type": "05e3967f-27b3-460d-94a5-d419c1588dce"},
                {"occurrence_type": "1bb4364c-26b9-4b31-a7c1-e8d7876594fc"},
            ]
        }
        inspection_occurrence_kind = get_obj_from_path(
            self.company.metadata, "inspection_occurrence_kind"
        )
        rep = Reporting.objects.first()
        occ = OccurrenceType.objects.filter(
            occurrence_kind__in=inspection_occurrence_kind
        ).first()
        menu = RecordMenu.objects.first()
        rep.occurrence_type = occ
        rep.form_data = new_form_data

        reporting_without_therapy = Reporting.objects.create(
            company=self.company,
            occurrence_type=occ,
            km=rep.km,
            status=rep.status,
            number="test",
        )

        with DisableSignals():
            rep.save()

        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CreateRecuperations", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "inspection": [str(rep.pk), str(reporting_without_therapy.pk)],
                        "menu": str(menu.pk),
                        "recuperations_to_create_occurrence_types": [str(occ.pk)],
                    },
                }
            },
        )
        response_reporting = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(rep.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response_reporting.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["data"]["attributes"]["inspectionWithRecuperations"]
        assert (
            content["data"]["attributes"]["statusInspectionWithRecuperations"] == "20"
        )

    def test_reportings_from_inspection_with_different_occurrence_kind(self, client):
        inspection_occurrence_kind = get_obj_from_path(
            self.company.metadata, "inspection_occurrence_kind"
        )
        rep = Reporting.objects.exclude(
            occurrence_type__occurrence_kind__in=inspection_occurrence_kind
        ).first()
        occ = OccurrenceType.objects.exclude(
            occurrence_kind__in=inspection_occurrence_kind
        ).first()
        menu = RecordMenu.objects.first()

        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CreateRecuperations", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "inspection": [str(rep.pk)],
                        "menu": str(menu.pk),
                        "recuperations_to_create_occurrence_types": [str(occ.pk)],
                    },
                }
            },
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            content["errors"][0]["detail"]
            == "kartado.error.reporting.reporting_not_inspection"
        )
        response_reporting = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(rep.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content_reporting = json.loads(response_reporting.content)

        assert (
            content_reporting["data"]["attributes"]["statusInspectionWithRecuperations"]
            == "00"
        )

    def test_recuperations_to_create_occurrence_types_param_is_required_under_correct_conditions(
        self, client
    ):
        inspection_occurrence_kind = get_obj_from_path(
            self.company.metadata, "inspection_occurrence_kind"
        )
        occ = OccurrenceType.objects.filter(
            occurrence_kind__in=inspection_occurrence_kind
        ).first()
        reporting_base = Reporting.objects.filter(company=self.company)[0]
        menu = RecordMenu.objects.first()

        reporting = Reporting.objects.create(
            company=self.company,
            occurrence_type=occ,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test",
        )
        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CreateRecuperations", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "inspection": [str(reporting.pk)],
                        "menu": str(menu.pk),
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_menu_is_required_for_creating_recuperations(self, client):
        rep = Reporting.objects.first()
        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CreateRecuperations", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"inspection": [str(rep.pk)]},
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reporting_recuperation_filter(self, client):
        new_form_data = {
            "therapy": [
                {"occurrence_type": "05e3967f-27b3-460d-94a5-d419c1588dce"},
                {"occurrence_type": "1bb4364c-26b9-4b31-a7c1-e8d7876594fc"},
            ]
        }
        inspection_occurrence_kind = get_obj_from_path(
            self.company.metadata, "inspection_occurrence_kind"
        )
        rep = Reporting.objects.first()
        occ = OccurrenceType.objects.filter(
            occurrence_kind__in=inspection_occurrence_kind
        ).first()
        rep.occurrence_type = occ
        rep.form_data = new_form_data
        with DisableSignals():
            rep.save()

        response_true = client.get(
            path="/{}/?company={}&created_recuperations=true".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        response_false = client.get(
            path="/{}/?company={}&created_recuperations=false".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content_true = json.loads(response_true.content)
        content_false = json.loads(response_false.content)

        assert response_true.status_code == status.HTTP_200_OK
        assert response_false.status_code == status.HTTP_200_OK
        assert content_true["meta"]["pagination"]["count"] == 1
        assert content_false["meta"]["pagination"]["count"] == 0

    def test_reporting_job_filter_null(self, client):
        response = client.get(
            path="/{}/?company={}&job=null&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 3

    def test_post_reporting_with_geometry(self, client):
        road = Road.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).first()
        occurrence_type = OccurrenceType.objects.filter(company=self.company).first()
        service_order_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "roadName": str(road.name),
                        "km": 145,
                        "direction": str(road.direction),
                        "lane": "1",
                        "formData": {"x": 100, "y": 1},
                        "featureCollection": {
                            "type": "FeatureCollection",
                            "features": [
                                {
                                    "type": "Feature",
                                    "geometry": {
                                        "type": "Polygon",
                                        "coordinates": [
                                            [
                                                [4.120676, 27.623279],
                                                [4.032602, 27.623279],
                                                [4.032602, 28.499461],
                                                [4.120676, 28.499461],
                                                [4.120676, 27.623279],
                                            ]
                                        ],
                                    },
                                    "properties": [{}],
                                }
                            ],
                        },
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type.pk),
                            }
                        },
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(service_order_status.pk),
                            }
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])

        # Check point coordinates to geometry centroid
        assert obj_created.point.x == 4.076639
        assert round(obj_created.point.y, 5) == 28.06137

    def test_patch_reporting_with_geometry(self, client):
        # This Reporting has a not-null Point
        reporting = Reporting.objects.get(uuid="beb96881-8387-431e-9620-581684975780")
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(reporting.pk),
                    "attributes": {
                        "featureCollection": {
                            "type": "FeatureCollection",
                            "features": [
                                {
                                    "type": "Feature",
                                    "geometry": {
                                        "type": "Polygon",
                                        "coordinates": [
                                            [
                                                [4.120676, 27.623279],
                                                [4.032602, 27.623279],
                                                [4.032602, 28.499461],
                                                [4.120676, 28.499461],
                                                [4.120676, 27.623279],
                                            ]
                                        ],
                                    },
                                    "properties": {"teste": 1},
                                }
                            ],
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        obj_created = Reporting.objects.get(pk=content["data"]["id"])

        # Check point coordinates to geometry centroid
        assert obj_created.point.x == 4.076639
        assert round(obj_created.point.y, 5) == 28.06137
        assert obj_created.properties == [{"teste": 1}]

    def test_post_reporting_with_shape_file(self, client):
        road = Road.objects.filter(company=self.company).first()
        firm = Firm.objects.filter(company=self.company).first()
        occurrence_type = OccurrenceType.objects.filter(company=self.company).first()
        service_order_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company
        ).first()
        shape_file = ShapeFile.objects.filter(companies=self.company).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "roadName": str(road.name),
                        "km": 145,
                        "direction": str(road.direction),
                        "lane": "1",
                        "formData": {"x": 100, "y": 1},
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "road": {"data": {"type": "Road", "id": str(road.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occurrence_type.pk),
                            }
                        },
                        "status": {
                            "data": {
                                "type": "ServiceOrderActionStatus",
                                "id": str(service_order_status.pk),
                            }
                        },
                        "activeShapeFiles": {
                            "data": [{"type": "ShapeFile", "id": str(shape_file.pk)}]
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)

        shape_files = content["data"]["relationships"]["activeShapeFiles"]

        assert shape_files["meta"]["count"] == 1
        assert shape_files["data"][0]["id"] == str(shape_file.pk)

    def test_set_altimetry_success_with_one_coordinate(self):
        # Point( -51.8533, -15.3135 ) --> This point should return an altitude value of 285 meters
        with patch(
            "apps.occurrence_records.helpers.apis.tessadem.functions.requests"
        ) as mock_external_api:
            # Create request response
            request = Mock()
            request.body = None
            response = Response()
            response.request = request
            response.status_code = 200
            response.headers = None
            response._content = b'{"results": [{"elevation": 285}]}'
            mock_external_api.get.return_value = response
            # Enable altimetry for company
            self.company.metadata["altimetry_enable"] = True
            self.company.save()
            # When creating a record it goes through the set_altimetry method
            report = Reporting.objects.create(
                company=self.company,
                created_by=self.user,
                geometry=GeometryCollection(Point(-51.8533, -15.3135)),
                km=0,
            )
            assert report.properties[0]["elevation_m"] == 285

    def test_set_altimetry_success_with_two_coordinates(self):
        # Point( -52.942022, -26.568681 ) --> This point should return an altitude value of 472 meters
        # Point( -52.93814, -26.567558 ) --> This point should return an altitude value of 498 meters
        with patch(
            "apps.occurrence_records.helpers.apis.tessadem.functions.requests"
        ) as mock_external_api:
            # Create request response
            request = Mock()
            request.body = None

            response1 = Response()
            response1.request = request
            response1.status_code = 200
            response1.headers = None
            response1._content = b'{"results": [{"elevation": 472}]}'

            response2 = Response()
            response2.request = request
            response2.status_code = 200
            response2.headers = None
            response2._content = b'{"results": [{"elevation": 498}]}'

            mock_external_api.get.side_effect = [response1, response2]

            # Enable altimetry for company
            self.company.metadata["altimetry_enable"] = True
            self.company.save()
            # When creating a record it goes through the set_altimetry method
            report = Reporting.objects.create(
                company=self.company,
                created_by=self.user,
                geometry=GeometryCollection(
                    Point(-52.942022, -26.568681), Point(-52.93814, -26.567558)
                ),
                km=0,
            )

            # Check if the elevations are set correctly
            assert report.properties[0]["elevation_m"] == 472
            assert report.properties[1]["elevation_m"] == 498

    def test_reporting_has_resource_true(self, client):
        response = client.get(
            path="/{}/?company={}&has_resource=true&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 3

    def test_reporting_has_resource_false(self, client):
        response = client.get(
            path="/{}/?company={}&has_resource=false&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_create_jobs_from_inspections(self, client):
        new_form_data = {
            "therapy": [
                {"occurrence_type": "05e3967f-27b3-460d-94a5-d419c1588dce"},
                {"occurrence_type": "1bb4364c-26b9-4b31-a7c1-e8d7876594fc"},
            ]
        }
        inspection_occurrence_kind = get_obj_from_path(
            self.company.metadata, "inspection_occurrence_kind"
        )
        rep = Reporting.objects.first()
        occ = OccurrenceType.objects.filter(
            occurrence_kind__in=inspection_occurrence_kind
        ).first()
        rep.occurrence_type = occ
        rep.form_data = new_form_data
        with DisableSignals():
            rep.save()

        rep_uuid = str(rep.uuid)
        menu_uuid = str(RecordMenu.objects.first().uuid)
        firm_uuid = str(Firm.objects.first().uuid)
        subcompany_uuid = str(SubCompany.objects.first().uuid)
        user_uuid = str(User.objects.first().uuid)

        body = {
            "data": {
                "type": self.model,
                "inspection_data": {
                    rep_uuid: "Fase 1",
                },
                "menu": menu_uuid,
                "job_data": {
                    "start_date": "2025-1-1T10:22:30.051Z",
                    "end_date": "2025-1-31T23:44:31.061Z",
                    "worker": user_uuid,
                    "firm": firm_uuid,
                    "watcher_users": [user_uuid],
                    "watcher_subcompanies": [subcompany_uuid],
                    "watcher_firms": [firm_uuid],
                },
            }
        }

        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CreateJobsFromInspections", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=body,
        )

        assert response.status_code == status.HTTP_200_OK

    def test_copyreportings_success(self, client):
        reporting = Reporting.objects.first()

        body = {"data": {"uuids": [reporting.uuid]}}

        # Test a correct request
        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CopyReportings", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=body,
        )

        assert response.status_code == status.HTTP_200_OK

    def test_copyreportings_without_company(self, client):
        reporting = Reporting.objects.first()

        body = {"data": {"uuids": [reporting.uuid]}}

        # Test a request without company
        response = client.post(
            path="/{}/{}/".format(self.model, "CopyReportings"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=body,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_copyreportings_without_body_data(self, client):

        # Test a request without body data
        body = {}

        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CopyReportings", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=body,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_copyreportings_without_body_uuids(self, client):
        # Test a request without body uuids
        body = {"data": {}}

        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CopyReportings", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=body,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_copyreportings_without_uuids(self, client):
        # Test a request with body uuids with a string
        body = {"data": {"uuids": "Teste"}}

        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CopyReportings", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=body,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_copyreportings_with_more_then_20_uuids(self, client):

        # Test a request with body uuids lager then 20 units
        body = {
            "data": {
                "uuids": [
                    "Teste 1",
                    "Teste 2",
                    "Teste 3",
                    "Teste 4",
                    "Teste 5",
                    "Teste 6",
                    "Teste 7",
                    "Teste 8",
                    "Teste 9",
                    "Teste 10",
                    "Teste 11",
                    "Teste 12",
                    "Teste 13",
                    "Teste 14",
                    "Teste 15",
                    "Teste 16",
                    "Teste 17",
                    "Teste 18",
                    "Teste 19",
                    "Teste 20",
                    "Teste 21",
                ]
            }
        }

        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CopyReportings", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=body,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_copyreportings_with_nonexistent_ids(self, client):

        # Test a request with body nonexistent reporting id
        body = {"data": {"uuids": ["unexistend_id"]}}

        response = client.post(
            path="/{}/{}/?company={}".format(
                self.model, "CopyReportings", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=body,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_has_image(self, client):
        response = client.get(
            path="/{}/?company={}&has_image=true&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_step_changed_date(self, client):
        response = client.get(
            path="/{}/?company={}&approval_step_changed_date=2025-05-27".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_only_related_to(self, client):
        response = client.get(
            path="/{}/?company={}&only_related_to={}&page_size=1".format(
                self.model, str(self.company.pk), "0aa50773-b368-4a50-9f12-4a7d8dfaf256"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 4

    def test_csp_filter(self, client):

        response = client.get(
            path="/{}/?company={}&csp=8.1&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 4

    def test_get_num_jobs_filter(self, client):

        response = client.get(
            path="/{}/?company={}&num_jobs=2".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_get_jobs_rdos_user_firms_filter(self, client):

        response = client.get(
            path="/{}/?company={}&jobs_rdos_user_firms=1|1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_get_num_jobs_only_user_firms_filter(self, client):

        job_uuid = str(Job.objects.first().uuid)
        response = client.get(
            path="/{}/?company={}&num_jobs_only_user_firms=2,{}".format(
                self.model, str(self.company.pk), job_uuid
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_get_num_user_firms_filter(self, client):

        response = client.get(
            path="/{}/?company={}&num_user_firms=2".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_get_range_kms(self, client):

        response = client.get(
            path="/{}/?company={}&range_kms=70,300".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_no_construction_progress_filter(self, client):

        response = client.get(
            path="/{}/?company={}&no_construction_progress=true".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 3

        response = client.get(
            path="/{}/?company={}&no_construction_progress=false".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_no_construction_progress_include_uuid_filter(self, client):

        reporting = Reporting.objects.filter(company=self.company).first()

        # Test with specific UUID
        response = client.get(
            path="/{}/?company={}&no_construction_progress_include_uuid={}".format(
                self.model, str(self.company.pk), str(reporting.uuid)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 4

    def test_update_reporting_to_inventory_when_in_job_fails(self, client):
        """
        Ensure that updating a Reporting's occurrence_type to an inventory
        (occurrence_kind=2) when it is part of a Job raises validation error
        """
        # Get a reporting that is in a job
        reporting = (
            Reporting.objects.filter(
                company=self.company,
                job__isnull=False,
            )
            .exclude(occurrence_type__occurrence_kind="2")
            .first()
        )

        # Get an inventory occurrence_type
        inventory_occurrence_type = OccurrenceType.objects.filter(
            company=self.company,
            occurrence_kind="2",
        ).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=json.dumps(
                {
                    "data": {
                        "type": self.model,
                        "id": str(reporting.pk),
                        "attributes": {},
                        "relationships": {
                            "occurrenceType": {
                                "data": {
                                    "type": "OccurrenceType",
                                    "id": str(inventory_occurrence_type.pk),
                                }
                            }
                        },
                    }
                }
            ),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert "kartado.error.inventory_in_job_exception" in str(content)

    def test_update_reporting_to_inventory_when_not_in_job_succeeds(self, client):
        """
        Ensure that updating a Reporting's occurrence_type to an inventory
        (occurrence_kind=2) when it is NOT part of a Job works normally
        """
        # Get a reporting that is NOT in a job
        reporting = (
            Reporting.objects.filter(
                company=self.company,
                job__isnull=True,
            )
            .exclude(occurrence_type__occurrence_kind="2")
            .first()
        )

        # Get an inventory occurrence_type
        inventory_occurrence_type = OccurrenceType.objects.filter(
            company=self.company,
            occurrence_kind="2",
        ).first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(reporting.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=json.dumps(
                {
                    "data": {
                        "type": self.model,
                        "id": str(reporting.pk),
                        "attributes": {},
                        "relationships": {
                            "occurrenceType": {
                                "data": {
                                    "type": "OccurrenceType",
                                    "id": str(inventory_occurrence_type.pk),
                                }
                            }
                        },
                    }
                }
            ),
        )

        assert response.status_code == status.HTTP_200_OK
