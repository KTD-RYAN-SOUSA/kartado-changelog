import json

import pytest
from rest_framework import status

from apps.resources.models import Contract, FieldSurvey
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestFieldSurvey(TestBase):
    model = "FieldSurvey"

    ATTRIBUTES = {"grades": {"teste": "teste"}}

    def test_field_survey_list(self, client):
        """
        Ensures we can list using the FieldSurvey endpoint
        and the fixture is properly listed
        """
        print(self.company.pk)
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
        assert content["meta"]["pagination"]["count"] == 3

    def test_field_survey_without_company(self, client):
        """
        Ensures calling the FieldSurvey endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_field_survey(self, client):
        """
        Ensures a specific FieldSurvey can be fetched using the uuid
        """

        instance = FieldSurvey.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_field_survey(self, client):
        """
        Ensures a new FieldSurvey can be created using the endpoint
        """

        contract = Contract.objects.filter(subcompany__isnull=False)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "FieldSurvey",
                    "attributes": {"grades": {"teste": "teste"}},
                    "relationships": {
                        "contract": {
                            "data": {
                                "type": "Contract",
                                "id": str(contract[0].pk),
                            }
                        }
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_field_survey_without_company_id(self, client):
        """
        Ensures a new FieldSurvey cannot be created
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

    def test_create_field_survey_without_permission(self, client):
        """
        Ensures a new FieldSurvey cannot be created without
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

    def test_update_field_survey(self, client):
        """
        Ensure a FieldSurvey can be updated using the endpoint
        """

        instance = FieldSurvey.objects.filter(measurement_bulletin__isnull=True).first()

        self.ATTRIBUTES["grades"] = {"modificado": "modificado"}

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

    def test_delete_field_survey(self, client):
        """
        Ensure a FieldSurvey can be deleted using the endpoint
        """

        instance = FieldSurvey.objects.exclude(
            approval_status="APPROVED_APPROVAL"
        ).first()

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

    def test_create_manual_field_survey(self, client):
        """
        Ensures a new manual FieldSurvey can be created using the endpoint
        """

        contract = Contract.objects.filter(subcompany__isnull=False)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "FieldSurvey",
                    "attributes": {
                        "grades": {"teste": "teste"},
                        "manual": "true",
                        "final_grade": "50",
                    },
                    "relationships": {
                        "contract": {
                            "data": {
                                "type": "Contract",
                                "id": str(contract[0].pk),
                            }
                        }
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_cannot_create_field_survey_with_invalid_final_grade(self, client):
        """
        Ensures a new manual FieldSurvey cannot be created using a invalid final_grade
        """

        contract = Contract.objects.filter(subcompany__isnull=False)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "FieldSurvey",
                    "attributes": {
                        "grades": {"teste": "teste"},
                        "manual": "true",
                        "final_grade": "-10",
                    },
                    "relationships": {
                        "contract": {
                            "data": {
                                "type": "Contract",
                                "id": str(contract[0].pk),
                            }
                        }
                    },
                }
            },
        )

        content = json.loads(response.content)
        error_message = (
            "kartado.error.field_survey.final_grade_value_must_be_between_0_and_100"
        )
        assert content["errors"][0]["detail"] == error_message
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.parametrize(
        "type_survey_value,expected_count",
        [("ALL", 4), ("DETAILED", 3), ("MANUAL", 1)],
    )
    def test_field_survey_list_type_survey_filter(
        self, client, type_survey_value, expected_count
    ):
        """
        Ensures that FieldSurveys are listed according to the type_survey
        filter choices
        """
        response = client.get(
            path="/{}/?company={}&page_size=1&type_survey={}".format(
                self.model, str(self.company.pk), type_survey_value
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] == expected_count

    def test_field_survey_list_type_survey_filter_invalid_choice(self, client):
        """
        Ensures that an error is returned when choosing an invalid option
        from the type_survey filter
        """
        invalid_choice = "INVALID_CHOICE"
        response = client.get(
            path="/{}/?company={}&page_size=1&type_survey={}".format(
                self.model, str(self.company.pk), invalid_choice
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        error_message = "kartado.error.field_survey.type_survey_filter.invalid_choice"
        assert content["errors"][0]["detail"] == error_message
