import json

import pytest
from django.db.models import Q
from rest_framework import status

from helpers.testing.fixtures import TestBase, add_false_permission, false_permission

from ..models import SubCompany

pytestmark = pytest.mark.django_db


class TestSubCompany(TestBase):
    model = "SubCompany"

    ATTRIBUTES = {
        "subcompanyType": "HIRING",
        "cnpj": "91742417000185",
        "contractStartDate": "2022-01-01",
        "contractEndDate": "2022-06-01",
        "office": "an office",
        "constructionName": "a construction name",
    }

    def test_subcompany_list(self, client):
        """
        Ensures we can list using the SubCompany endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 1

    def test_subcompany_without_company(self, client):
        """
        Ensures calling the SubCompany endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_subcompany(self, client):
        """
        Ensures a specific SubCompany can be fetched using the uuid
        """

        instance = SubCompany.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        print(response)
        assert response.status_code == status.HTTP_200_OK

    def test_create_subcompany(self, client):
        """
        Ensures a new SubCompany can be created using the endpoint
        """

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {"data": {"type": "Company", "id": self.company.pk}}
                    },
                }
            },
        )

        # Object was created successfully
        content = json.loads(response.content)
        obj_created = SubCompany.objects.get(pk=content["data"]["id"])
        assert obj_created.legacy_uuid is None

        assert response.status_code == status.HTTP_201_CREATED

    def test_create_subcompany_with_alphanumeric_cnpj(self, client):
        """KAP-46: garante que SubCompany aceita CNPJ no novo formato
        alfanumérico (IN RFB 2.229/2024)."""
        attributes = dict(self.ATTRIBUTES)
        attributes["cnpj"] = "12.ABC.345/01DE-35"  # exemplo oficial Serpro

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": attributes,
                    "relationships": {
                        "company": {"data": {"type": "Company", "id": self.company.pk}}
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)
        assert content["data"]["attributes"]["cnpj"] == "12.ABC.345/01DE-35"

    def test_create_subcompany_with_invalid_alphanumeric_cnpj(self, client):
        """KAP-46 / RN04: CNPJ alfanumérico com DV errado é rejeitado."""
        attributes = dict(self.ATTRIBUTES)
        attributes["cnpj"] = "12.ABC.345/01DE-99"

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": attributes,
                    "relationships": {
                        "company": {"data": {"type": "Company", "id": self.company.pk}}
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_subcompany_with_blank_legacy_uuid(self, client):
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "subcompanyType": "HIRING",
                        "cnpj": "91742417000185",
                        "contractStartDate": "2022-01-01",
                        "contractEndDate": "2022-06-01",
                        "office": "an office",
                        "constructionName": "a construction name",
                        "legacy_uuid": "",
                    },
                    "relationships": {
                        "company": {"data": {"type": "Company", "id": self.company.pk}}
                    },
                }
            },
        )
        content = json.loads(response.content)
        assert content["data"]["attributes"]["legacyUuid"] == ""
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_subcompany_without_company_id(self, client):
        """
        Ensures a new SubCompany cannot be created
        without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_subcompany_without_permission(self, client):
        """
        Ensures a new SubCompany cannot be created without
        the proper permissions
        """

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_subcompany(self, client):
        """
        Ensure a SubCompany can be updated using the endpoint
        """

        instance = SubCompany.objects.filter(company=self.company).first()

        # Change days_of_work from 25 to 32 for the update
        self.ATTRIBUTES["days_of_work"] = 32

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(instance.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_subcompany(self, client):
        """
        Ensure a SubCompany can be deleted using the endpoint
        """

        instance = SubCompany.objects.filter(company=self.company).first()

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

    def test_subcompany_dates(self, client):
        """
        Ensure a SubCompany contract_start_date can't be after the contract_end_date
        """

        # Backup old starts_at and ends_at values
        old_starts_at = self.ATTRIBUTES["contractStartDate"]
        old_ends_at = self.ATTRIBUTES["contractEndDate"]
        # Change starts_at and ends_at to offending dates
        self.ATTRIBUTES["contractStartDate"] = "2022-01-01"
        self.ATTRIBUTES["contractEndDate"] = "2021-01-01"

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {"data": {"type": "Company", "id": self.company.pk}}
                    },
                }
            },
        )

        content = json.loads(response.content)

        # Error creating object
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        expected_message = "kartado.error.subcompany.contract_end_date_should_be_after_contract_start_date"
        assert content["errors"][0]["detail"] == expected_message

        # Reset changed values
        self.ATTRIBUTES["contractStartDate"] = old_starts_at
        self.ATTRIBUTES["contractEndDate"] = old_ends_at

    def test_hired_required_to_fill_hired_by_subcompany(self, client):
        instance = SubCompany.objects.filter(company=self.company).first()
        self.ATTRIBUTES["subcompanyType"] = "HIRED"

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(instance.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        content = json.loads(response.content)

        # Error creating object
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        expected_message = "kartado.error.subcompany.hired_subcompanies_need_to_fill_hired_by_subcompany_field"
        assert content["errors"][0]["detail"] == expected_message

        # Change the value back to normal
        self.ATTRIBUTES["subcompanyType"] = "HIRING"

    def test_filter_can_rdo_create_with_can_create_and_edit_all_firms_permission(
        self, client
    ):

        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_create_and_edit_all_firms": True},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_create={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = SubCompany.objects.filter(company_id=self.company.pk).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_view_with_can_view_all_firms_permission(self, client):

        add_false_permission(
            self.user, self.company, "MultipleDailyReport", {"can_view_all_firms": True}
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_view={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = SubCompany.objects.filter(company_id=self.company.pk).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_create_without_can_create_and_edit_all_firms_permission(
        self, client
    ):

        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_create_and_edit_all_firms": False, "can_view_all_firms": False},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_create={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = SubCompany.objects.filter(
            Q(subcompany_firms__users__uuid=self.user.uuid)
            | Q(subcompany_firms__inspectors__uuid=self.user.uuid)
            | Q(subcompany_firms__manager_id=self.user.uuid)
        ).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_view_without_can_view_all_firms_permission(self, client):

        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_create_and_edit_all_firms": False, "can_view_all_firms": False},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_view={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = SubCompany.objects.filter(
            Q(subcompany_firms__users__uuid=self.user.uuid)
            | Q(subcompany_firms__inspectors__uuid=self.user.uuid)
            | Q(subcompany_firms__manager_id=self.user.uuid)
        ).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_view_without_can_view_all_firms_permission_set(
        self, client
    ):

        response = client.get(
            path="/{}/?company={}&can_rdo_view={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = SubCompany.objects.filter(company_id=self.company.pk).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_view_when_value_is_false(self, client):

        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_view_all_firms": False},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_view={}".format(
                self.model, str(self.company.pk), "false"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK

        expected_count = SubCompany.objects.filter(company_id=self.company.pk).count()
        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_create_without_can_view_all_firms_permission_set(
        self, client
    ):

        response = client.get(
            path="/{}/?company={}&can_rdo_create={}".format(
                self.model, str(self.company.pk), "true"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(
                self.token,
            ),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK

        expected_count = SubCompany.objects.filter(company_id=self.company.pk).count()

        assert content["meta"]["pagination"]["count"] == expected_count

    def test_filter_can_rdo_create_when_value_is_false(self, client):

        add_false_permission(
            self.user,
            self.company,
            "MultipleDailyReport",
            {"can_create_and_edit_all_firms": False},
        )

        response = client.get(
            path="/{}/?company={}&can_rdo_create={}".format(
                self.model, str(self.company.pk), "false"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_200_OK

        expected_count = SubCompany.objects.filter(company_id=self.company.pk).count()
        assert content["meta"]["pagination"]["count"] == expected_count
