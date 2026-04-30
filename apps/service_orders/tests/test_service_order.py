import json

import pytest
from rest_framework import status

from apps.occurrence_records.models import OccurrenceRecord
from apps.service_orders.const import kind_types
from apps.service_orders.models import ServiceOrder
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestServiceOrder(TestBase):
    model = "ServiceOrder"

    def test_list_service_order(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_service_order_without_queryset(self, client):

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

    def test_list_service_order_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service_order(self, client):

        obj = ServiceOrder.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_service_order_without_company(self, client):

        obj = ServiceOrder.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_service_order_without_company_uuid(self, client):

        obj = ServiceOrder.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_service_order(self, client):

        obj = ServiceOrder.objects.filter(company=self.company, is_closed=False).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"closedDescription": "test"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_service_order_without_permission(self, client):

        obj = ServiceOrder.objects.filter(company=self.company, is_closed=True).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"closedDescription": "test"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_service_order(self, client):

        obj = ServiceOrder.objects.filter(company=self.company).order_by("-opened_at")[
            0
        ]

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_create_service_order(self, client):

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"description": "test ServiceOrder"},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ServiceOrder.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # default kind
        assert obj_created.kind == kind_types.ENVIRONMENT

    def test_create_service_order_with_record(self, client):

        record = OccurrenceRecord.objects.filter(
            company=self.company,
            form_data__property_intersections__isnull=False,
        ).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"description": "test ServiceOrder"},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "addOccurrenceRecords": {
                            "data": [
                                {
                                    "id": str(record.pk),
                                    "type": "OccurrenceRecord",
                                }
                            ]
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ServiceOrder.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_kind_in_create_service_order(self, client):

        record = OccurrenceRecord.objects.filter(
            company=self.company,
            service_orders__isnull=True,
            form_data__has_key="shape_file_property",
            form_data__shape_file_property__isnull=False,
            form_data__property_intersections__isnull=False,
        ).first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "description": "test ServiceOrder",
                        "kind": kind_types.ENVIRONMENT,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "addOccurrenceRecords": {
                            "data": [
                                {
                                    "id": str(record.pk),
                                    "type": "OccurrenceRecord",
                                }
                            ]
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = ServiceOrder.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # kind
        assert obj_created.kind == kind_types.ENVIRONMENT

        # Record without shape_file_property

        record = (
            OccurrenceRecord.objects.filter(
                company=self.company, service_orders__isnull=True
            )
            .exclude(
                form_data__has_key="shape_file_property",
                form_data__shape_file_property__isnull=False,
            )
            .first()
        )

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "description": "test ServiceOrder",
                        "kind": kind_types.LAND,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "addOccurrenceRecords": {
                            "data": [
                                {
                                    "id": str(record.pk),
                                    "type": "OccurrenceRecord",
                                }
                            ]
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_error_kind_in_create_service_order_with_two_records(self, client):

        # ServiceOrder with 2 records

        records = OccurrenceRecord.objects.filter(
            company=self.company, service_orders__isnull=True
        )
        record0 = records[0]
        record1 = records[1]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "description": "test ServiceOrder",
                        "kind": kind_types.LAND,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "addOccurrenceRecords": {
                            "data": [
                                {
                                    "id": str(record0.pk),
                                    "type": "OccurrenceRecord",
                                },
                                {
                                    "id": str(record1.pk),
                                    "type": "OccurrenceRecord",
                                },
                            ]
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_initial_status_for_land_service(self):
        # Create a ServiceOrder object of type "LAND"
        land_service = ServiceOrder.objects.create(
            company=self.company,
            kind=kind_types.LAND,
        )

        # Check whether the initial status is set correctly
        assert land_service.status.name == "Em notificação verbal"

    def test_initial_status_for_environmental_service(self):
        # Create a ServiceOrder object of type "ENVIRONMENTAL"
        environmental_service = ServiceOrder.objects.create(
            company=self.company,
            kind=kind_types.ENVIRONMENT,
        )

        # Check whether the initial status is set correctly
        assert environmental_service.status.name == "Em andamento"
