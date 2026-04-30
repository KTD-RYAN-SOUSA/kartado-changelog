import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase, false_permission
from helpers.testing.validators import response_has_object, validate_response

from ..models import Construction, ConstructionProgress

pytestmark = pytest.mark.django_db


class TestConstruction(TestBase):
    model = "ConstructionProgress"

    ATTRIBUTES = {
        "name": "Construction Progress Test",
        "progress_details": [{"someDetail": "Detail text"}],
    }

    def test_construction_progress_should_return_custom_serializer(self, client):
        serializer_fields = {
            "attributes": [
                "uuid",
                "name",
                "executed_at",
                "responsible",
                "amount_photos",
                "amount_reportings",
                "amount_files",
                "percentage_done",
            ],
            "relations": ["files"],
        }

        instance = ConstructionProgress.objects.first()

        response = client.get(
            path="/{}/{}/?company={}&exclude_last_progress=true".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        assert (
            validate_response(expect_response=serializer_fields, response=content)
            is True
        )

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_construction_progress_should_not_return_custom_serializer(self, client):
        serializer_fields = {
            "attributes": [
                "uuid",
                "name",
                "executed_at",
                "responsible",
                "amount_photos",
                "amount_reportings",
                "amount_files",
                "percentage_done",
            ],
            "relations": ["files"],
        }

        instance = ConstructionProgress.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        assert (
            validate_response(expect_response=serializer_fields, response=content)
            is False
        )

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_construction_progress_list_should_not_return_latest_object(self, client):
        """
        Ensures we can list using the ConstructionProgress endpoint
        and the fixture is properly listed
        """

        latest_instace = ConstructionProgress.objects.order_by("-created_at").first()

        response = client.get(
            path="/{}/?company={}&page_size=1&exclude_last_progress=true".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        assert response_has_object(content, str(latest_instace.pk)) is False

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_construction_progress_list_should_return_latest_object(self, client):
        """
        Ensures we can list using the ConstructionProgress endpoint
        and the fixture is properly listed
        """

        latest_instace = ConstructionProgress.objects.order_by("-created_at").first()

        response = client.get(
            path="/{}/?company={}&page_size=1&exclude_last_progress=false".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        assert response_has_object(content, str(latest_instace.pk)) is True

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_construction_progress_list_should_only_return_latest_object(self, client):
        latest_instace = ConstructionProgress.objects.order_by("-created_at").first()

        response = client.get(
            path="/{}/?company={}&page_size=1&only_last_progress=true".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        assert response_has_object(content, str(latest_instace.pk)) is True
        assert content["meta"]["pagination"]["count"] == 1

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_construction_progress_list_should_return_all_objects(self, client):
        amount_of_objetcs = ConstructionProgress.objects.count()

        response = client.get(
            path="/{}/?company={}&page_size=1&only_last_progress=false".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert content["meta"]["pagination"]["count"] == amount_of_objetcs

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_validate_construction_progress_endpoint_data(self, client):
        EXPECTED_CONSTRUCTION_PROGRESS_ATTRIBUTES = {
            "uuid": "0c3a48c4-14f6-4cfe-ad28-70df971b291c",
            "name": "Test validate progress data",
            "executedAt": "2022-07-07T17:05:03.235000-03:00",
            "responsible": "Romário",
            "amountPhotos": 0,
            "amountReportings": 1,
            "amountFiles": 0,
            "percentageDone": 0.25,
        }

        construction_progress_instace = ConstructionProgress.objects.filter(
            name="Test validate progress data"
        ).first()

        response = client.get(
            path="/{}/{}/?company={}&page_size=1&only_last_progress=false".format(
                self.model,
                str(construction_progress_instace.pk),
                str(self.company.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        assert (
            EXPECTED_CONSTRUCTION_PROGRESS_ATTRIBUTES == content["data"]["attributes"]
        )

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_construction_progress_list(self, client):
        """
        Ensures we can list using the ConstructionProgress endpoint
        and the fixture is properly listed
        """
        construction_progress_count = ConstructionProgress.objects.count()

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
        assert content["meta"]["pagination"]["count"] == construction_progress_count

    def test_list_construction_progress_without_company(self, client):
        """
        Ensures calling the ConstructionProgress endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_construction_progress(self, client):
        """
        Ensures a specific ConstructionProgress can be fetched using the uuid
        """

        instance = ConstructionProgress.objects.first()

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

    def test_create_construction_progress(self, client):
        """
        Ensures a new ConstructionProgress can be created using the endpoint
        """

        construction_id = Construction.objects.first().uuid

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "construction": {
                            "data": {
                                "type": "Construction",
                                "id": str(construction_id),
                            }
                        }
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_construction_progress_without_company_id(self, client):
        """
        Ensures a new ConstructionProgress cannot be created without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_construction_progress_without_permission(self, client):
        """
        Ensures a new ConstructionProgress cannot be created without
        the proper permissions
        """

        false_permission(self.user, self.company, self.model)

        construction_id = Construction.objects.first().uuid

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "construction": {
                            "data": {
                                "type": "Construction",
                                "id": str(construction_id),
                            }
                        }
                    },
                }
            },
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_construction_progress(self, client):
        """
        Ensure a ConstructionProgress can be updated using the endpoint
        """

        instance = ConstructionProgress.objects.first()

        # Change name from "Construction Progress Test" to "Construction Progress Update"
        self.ATTRIBUTES["name"] = "Construction Progress Update"

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

        # Reset name to "Construction Test"
        self.ATTRIBUTES["name"] = "Construction Progress Test"

    def test_delete_construction_progress(self, client):
        """
        Ensure a ConstructionProgress can be deleted using the endpoint
        """

        instance = ConstructionProgress.objects.first()

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
