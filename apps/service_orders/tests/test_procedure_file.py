import json

import pytest
from rest_framework import status

from apps.occurrence_records.models import OccurrenceRecord
from apps.service_orders.models import Procedure, ProcedureFile
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestProcedureFile(TestBase):
    model = "ProcedureFile"

    def test_list_procedure_file(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_filter_procedure_file(self, client):

        record = OccurrenceRecord.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/?company={}&occurrence_record={}&page_size=1".format(
                self.model, str(self.company.pk), str(record.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&file_type={}&page_size=1".format(
                self.model, str(self.company.pk), "image"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        response = client.get(
            path="/{}/?company={}&file_type={}&page_size=1".format(
                self.model, str(self.company.pk), "file"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_procedure_file_without_queryset(self, client):

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

    def test_list_procedure_file_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_procedure_file(self, client):

        obj = ProcedureFile.objects.filter(
            procedures__action__service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(obj.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_procedure_file_without_company(self, client):

        obj = ProcedureFile.objects.filter(
            procedures__action__service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_procedure_file_without_company_uuid(self, client):

        obj = ProcedureFile.objects.filter(
            procedures__action__service_order__company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(obj.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_procedure_file(self, client):

        obj = ProcedureFile.objects.filter(
            procedures__action__service_order__company=self.company,
            procedures__action__service_order__is_closed=False,
        ).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"description": "test"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_procedure_file_without_permission(self, client):

        obj = ProcedureFile.objects.filter(
            procedures__action__service_order__company=self.company,
            procedures__action__service_order__is_closed=True,
        )[0]

        response = client.patch(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(obj.pk),
                    "attributes": {"description": "test"},
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

    def test_delete_procedure_file(self, client):

        obj = ProcedureFile.objects.filter(
            procedures__action__service_order__company=self.company,
            procedures__action__service_order__is_closed=False,
        ).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(obj.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_create_procedure_file(self, client):

        procedure = Procedure.objects.filter(
            firm__company=self.company, action__service_order__is_closed=False
        )[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "description": "Imagem de test.",
                        "upload": {"filename": "test.test"},
                    },
                    "relationships": {
                        "procedure": {
                            "data": {
                                "type": "Procedure",
                                "id": str(procedure.pk),
                            }
                        }
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = ProcedureFile.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

    def test_create_procedure_file_without_permission(self, client):

        procedure = Procedure.objects.filter(
            firm__company=self.company, action__service_order__is_closed=True
        )[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "description": "Imagem de test.",
                        "upload": {"filename": "test.test"},
                    },
                    "relationships": {
                        "procedure": {
                            "data": {
                                "type": "Procedure",
                                "id": str(procedure.pk),
                            }
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
