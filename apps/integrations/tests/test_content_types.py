import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestContentType(TestBase):
    model = "ContentType"

    def test_list_content_types(self, client):
        response = client.get(
            path="/{}/?page_size=1".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_id_filter(self, client):
        response = client.get(
            path="/{}/?page_size=1&id=1".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert content["meta"]["pagination"]["count"] == 1

    def test_model_filter(self, client):
        response = client.get(
            path="/{}/?page_size=1&model=dailyreportworker,dailyreportvehicle".format(
                self.model
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert content["meta"]["pagination"]["count"] == 2

    def test_app_label_filter(self, client):
        response = client.get(
            path="/{}/?page_size=1&app_label=quality_control".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert content["meta"]["pagination"]["count"] == 5

    def test_content_type_patch(self, client):

        response = client.patch(
            path="/{}/{}/".format(self.model, "1"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": "1",
                    "attributes": {
                        "appLabel": "integrations",
                        "model": "artespintegrationhistory",
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_content_type_delete(self, client):

        response = client.delete(
            path="/{}/{}/".format(self.model, "1"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_content_type_post(self, client):

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": "29611",
                    "attributes": {
                        "appLabel": "teste",
                        "model": "testeTeste",
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
