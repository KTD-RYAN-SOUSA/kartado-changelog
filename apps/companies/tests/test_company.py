import json

import pytest
from rest_framework import status

from apps.companies.const.metadata_fields import METADATA_FIELD_TO_TYPE
from apps.companies.models import Company, Firm
from apps.permissions.models import UserPermission
from helpers.testing.fixtures import TestBase
from helpers.testing.types import TYPE_SAMPLES

pytestmark = pytest.mark.django_db


class TestCompany(TestBase):
    model = "Company"

    def test_list_companies(self, client):
        response = client.get(
            path="/{}/?page_size=1".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_company(self, client):
        response = client.get(
            path="/{}/{}/".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_company(self, client):
        cnpj_valid = "09.481.248/0001-96"

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "name": "test",
                        "cnpj": cnpj_valid,
                        "active": True,
                        "customOptions": {},
                        "metadata": {},
                    },
                    "relationships": {
                        "owner": {"data": {"type": "User", "id": str(self.user.pk)}}
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Company.objects.get(pk=content["data"]["id"])
        assert obj_created.recordmenu_set.count() == 2
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_activates_company(self, client):

        company = Company.objects.filter(active=False).first()

        client.patch(
            path="/{}/{}/".format(self.model, str(company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(company.pk),
                    "attributes": {"active": True},
                }
            },
        )

        assert company.recordmenu_set.count() == 2

    def test_change_company_cnpj(self, client):
        cnpj_valid = "95.633.459/0001-39"

        response = client.patch(
            path="/{}/{}/".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(self.company.pk),
                    "attributes": {"cnpj": cnpj_valid},
                }
            },
        )

        # check update_firms_cnpj signal
        firms = Firm.objects.filter(company=self.company, is_company_team=True)
        content = json.loads(response.content)
        cnpj = content["data"]["attributes"]["cnpj"]
        for firm in firms:
            assert cnpj == firm.cnpj

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_change_company_cnpj_alphanumeric(self, client):
        """KAP-46: garante que alterar o CNPJ de uma Company para o novo
        formato alfanumérico (IN RFB 2.229/2024) salva normalmente e que o
        signal `update_firms_cnpj` propaga o novo valor para todas as
        Firms internas (`is_company_team=True`) — RN08."""
        cnpj_valid = "12.ABC.345/01DE-35"  # exemplo oficial Serpro

        response = client.patch(
            path="/{}/{}/".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(self.company.pk),
                    "attributes": {"cnpj": cnpj_valid},
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert content["data"]["attributes"]["cnpj"] == cnpj_valid

        # check update_firms_cnpj signal propagated alphanumeric value
        firms = Firm.objects.filter(company=self.company, is_company_team=True)
        for firm in firms:
            assert firm.cnpj == cnpj_valid

    def test_change_company_cnpj_lowercase_is_normalized(self, client):
        """KAP-46 / RN05: letras minúsculas são convertidas automaticamente
        para maiúsculas durante a validação."""
        response = client.patch(
            path="/{}/{}/".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(self.company.pk),
                    "attributes": {"cnpj": "12.abc.345/01de-35"},
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert content["data"]["attributes"]["cnpj"] == "12.ABC.345/01DE-35"

    def test_change_company_cnpj_invalid_returns_error(self, client):
        """KAP-46 / RN04: CNPJ com DV inválido é rejeitado pelo backend."""
        response = client.patch(
            path="/{}/{}/".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(self.company.pk),
                    "attributes": {"cnpj": "12.ABC.345/01DE-99"},
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_company_metadata_can_be_changed(self, client):
        """
        Make sure the Company metadata can be changed using the /ChangeMetadata/ endpoint and
        all field name and type requirements are met properly.
        """

        # Generate sample data for each field according to their type
        new_metadata = {
            field_name: TYPE_SAMPLES[field_type]
            for field_name, field_type in METADATA_FIELD_TO_TYPE.items()
        }
        new_metadata.pop("altimetry_enable")

        # Apply the metadata changes
        response = client.patch(
            path="/{}/{}/ChangeMetadata/?company={}".format(
                self.model, str(self.company.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": new_metadata},
        )
        resp_data = json.loads(response.content).get("data")

        assert (
            response.status_code == status.HTTP_200_OK
        ), "/ChangeMetada/ was not a HTTP 200"

        # Update the instance with the new values
        self.company.refresh_from_db()
        company_metadata = self.company.metadata
        assert type(company_metadata) is dict, "Company metadata is not a dictionary"

        for field_name, expected_data in new_metadata.items():
            # Ensure all fields were changed and obey type restrictions
            assert (
                field_name in company_metadata
            ), "Field not present in Company metadata"
            assert (
                type(company_metadata[field_name]) is METADATA_FIELD_TO_TYPE[field_name]
            ), "Company metadata has different type from expected"
            assert (
                company_metadata[field_name] == expected_data
            ), "Company metadata was different from expected"

            # Ensure all fields were also returned on the request
            assert (
                field_name in resp_data
            ), "Not all expected fields were included in response"
            assert (
                resp_data[field_name] == expected_data
            ), "Response field value was different from expected"

    def test_get_company_metadata(self, client):
        response = client.get(
            path="/{}/{}/ChangeMetadata/?company={}".format(
                self.model, str(self.company.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_reporting_section_fields_individual_rdo_export(self, client):
        response = client.get(
            path="/{}/{}/ReportingSectionFieldsIndividualRDOExport/".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_company_metadata_cant_change_altimetry(self, client):
        """
        Make sure the Company metadata can be changed using the /ChangeMetadata/ endpoint and
        all field name and type requirements are met properly.
        """

        # Generate sample data for each field according to their type
        data = {"altimetry_enable": True}

        # Apply the metadata changes
        response = client.patch(
            path="/{}/{}/ChangeMetadata/?company={}".format(
                self.model, str(self.company.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": data},
        )
        json.loads(response.content).get("data")

        assert (
            response.status_code == status.HTTP_200_OK
        ), "/ChangeMetada/ was not a HTTP 200"

        assert response.data["altimetry_enable"] is None

    def test_company_metadata_can_change_altimetry_enable(self, client):
        """
        Make sure the Company metadata can be changed using the /ChangeMetadata/ endpoint and
        all field name and type requirements are met properly.
        """

        # Generate sample data for each field according to their type
        data = {"altimetry_enable": True}
        company_id = str(self.company.pk)

        user_permission = self.company.permission_companies.first()
        user_permission.permissions["Company"].update({"can_enable_altimetry": True})
        user_permission.save()

        # Apply the metadata changes
        response = client.patch(
            path="/{}/{}/ChangeMetadata/?company={}".format(
                self.model, company_id, company_id
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": data},
        )
        json.loads(response.content).get("data")

        assert (
            response.status_code == status.HTTP_200_OK
        ), "/ChangeMetada/ was not a HTTP 200"

        assert response.data["altimetry_enable"] is True

    def test_user_permission_filter(self, client):

        permission = UserPermission.objects.first()

        response = client.get(
            path="/{}/?page_size=1&user_permission={}".format(
                self.model, str(permission.uuid)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == 1

    def test_get_company_id(self):
        assert self.company.get_company_id == self.company.uuid
