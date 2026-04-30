import json

import pytest
from django.db.models import Sum
from rest_framework import status

from apps.companies.models import Firm
from apps.resources.models import FieldSurvey
from apps.service_orders.models import (
    AdministrativeInformation,
    MeasurementBulletin,
    ProcedureResource,
    ServiceOrder,
)
from apps.service_orders.notifications import approved_measurement_bulletin
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestMeasurementBulletin(TestBase):
    model = "MeasurementBulletin"

    def test_list_measurement_bulletin(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_measurement_bulletin_without_queryset(self, client):

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

    def test_list_measurement_bulletin_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_measurement_bulletin(self, client):

        obj = MeasurementBulletin.objects.filter(contract__firm__company=self.company)[
            0
        ]

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_get_measurement_bulletin_preview(self, client):

        all_fs = FieldSurvey.objects.all()
        fs_ids = [str(fs.pk) for fs in all_fs]
        contract = FieldSurvey.objects.get(pk=fs_ids[0]).contract
        expected_provisioned_price = (
            contract.performance_services.aggregate(Sum("price")).get("price__sum")
            / contract.performance_months
        )
        response = client.get(
            path="/{}/Preview/?company={}&field_survey={}".format(
                self.model, str(self.company.pk), ",".join(fs_ids)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert content["data"]["provisionedPrice"] == expected_provisioned_price

        assert response.status_code == status.HTTP_200_OK

    def test_get_measurement_bulletin_without_company(self, client):

        obj = MeasurementBulletin.objects.filter(contract__firm__company=self.company)[
            0
        ]

        response = client.get(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_measurement_bulletin_without_company_uuid(self, client):

        obj = MeasurementBulletin.objects.filter(contract__firm__company=self.company)[
            0
        ]

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_measurement_bulletin(self, client):

        obj = MeasurementBulletin.objects.filter(contract__firm__company=self.company)[
            0
        ]

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"number": "test"},
                    "relationships": {
                        "contract": {
                            "data": {
                                "type": "Contract",
                                "id": str(obj.contract.pk),
                            }
                        }
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_measurement_bulletin(self, client):

        obj = MeasurementBulletin.objects.filter(contract__firm__company=self.company)[
            0
        ]

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {},
                    "relationships": {
                        "contract": {
                            "data": {
                                "type": "Contract",
                                "id": str(obj.contract.pk),
                            }
                        }
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_create_measurement_bulletin_using_firm(self, client):

        contract = MeasurementBulletin.objects.filter(
            contract__firm__company=self.company
        )[0].contract

        service_ids = AdministrativeInformation.objects.filter(
            contract__firm__isnull=False
        ).values_list("service_order_id", flat=True)
        service = ServiceOrder.objects.filter(company=self.company).exclude(
            pk__in=service_ids
        )[0]

        resource = ProcedureResource.objects.filter(
            resource__company=self.company, measurement_bulletin__isnull=True
        ).exclude(approval_status="WAITING_APPROVAL")[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "serviceOrder": {
                            "data": {
                                "type": "ServiceOrder",
                                "id": str(service.pk),
                            }
                        },
                        "contract": {
                            "data": {"type": "Contract", "id": str(contract.pk)}
                        },
                        "bulletinResources": {
                            "data": [
                                {
                                    "type": "ProcedureResource",
                                    "id": str(resource.pk),
                                }
                            ]
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = MeasurementBulletin.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()
        assert obj_created.related_firms.exists()

    def test_create_measurement_bulletin_using_subcompany(self, client):

        contract = MeasurementBulletin.objects.filter(
            contract__subcompany__company=self.company
        )[0].contract

        service_ids = AdministrativeInformation.objects.filter(
            contract__subcompany__isnull=False
        ).values_list("service_order_id", flat=True)
        service = ServiceOrder.objects.filter(company=self.company).exclude(
            pk__in=service_ids
        )[0]

        resource = ProcedureResource.objects.filter(
            resource__company=self.company, measurement_bulletin__isnull=True
        ).exclude(approval_status="WAITING_APPROVAL")[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "serviceOrder": {
                            "data": {
                                "type": "ServiceOrder",
                                "id": str(service.pk),
                            }
                        },
                        "contract": {
                            "data": {"type": "Contract", "id": str(contract.pk)}
                        },
                        "bulletinResources": {
                            "data": [
                                {
                                    "type": "ProcedureResource",
                                    "id": str(resource.pk),
                                }
                            ]
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = MeasurementBulletin.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

    def test_approved_measurement_bulletin_notification_uses_correct_company_field(
        self, client
    ):
        """
        Ensures we are not having notification problems by using the incorrect Company reference
        Related to KTD-5638
        """

        # Ensure the notification logic works when using a MeasurementBulletin related to a Contract with SubCompany
        bulletin = MeasurementBulletin.objects.filter(
            contract__subcompany__isnull=False, contract__firm__isnull=True
        ).first()
        notification_firms = Firm.objects.all()[:2]
        subject = "company test"
        description = "please work"
        approved_measurement_bulletin(
            bulletin, notification_firms, subject, description
        )

        # Ensure the incorrect way of referencing Company throws an error
        with pytest.raises(AttributeError):
            bulletin.contract.subcompany.companies.first()

    def test_create_measurement_bulletin_no_resources(self, client):

        contract = MeasurementBulletin.objects.filter(
            contract__firm__company=self.company
        )[0].contract

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "contract": {
                            "data": {"type": "Contract", "id": str(contract.pk)}
                        }
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = MeasurementBulletin.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()
        assert not obj_created.related_firms.exists()
