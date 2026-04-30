import json

import pytest
from rest_framework import status

from apps.ml_predictions.models import MLPrediction
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestMLPredictionView(TestBase):
    model = "MLPrediction"

    def test_list_predictions(self, client):
        MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": "test-rdo-1", "classe": 1, "descClasse": "revisao"},
        )
        MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": "test-rdo-2", "classe": 0, "descClasse": "aprovado"},
        )

        response = client.get(
            path="/MLPrediction/?company={}".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert len(content["data"]) >= 2

    def test_list_without_company_returns_forbidden(self, client):
        response = client.get(
            path="/MLPrediction/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_with_invalid_company_returns_forbidden(self, client):
        response = client.get(
            path="/MLPrediction/?company=invalid-uuid",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_retrieve_prediction(self, client):
        prediction = MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": "test-rdo-1", "classe": 1},
        )

        response = client.get(
            path="/MLPrediction/{}/?company={}".format(
                str(prediction.uuid), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert content["data"]["id"] == str(prediction.uuid)

    def test_patch_feedback(self, client):
        prediction = MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": "test-rdo-1"},
        )

        response = client.patch(
            path="/MLPrediction/{}/".format(str(prediction.uuid)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "MLPrediction",
                    "id": str(prediction.uuid),
                    "attributes": {
                        "feedback": True,
                        "feedbackNotes": "Predição correta",
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK
        prediction.refresh_from_db()
        assert prediction.feedback is True
        assert prediction.feedback_notes == "Predição correta"

    def test_patch_feedback_negative(self, client):
        prediction = MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": "test-rdo-1"},
        )

        response = client.patch(
            path="/MLPrediction/{}/".format(str(prediction.uuid)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "MLPrediction",
                    "id": str(prediction.uuid),
                    "attributes": {
                        "feedback": False,
                        "feedbackNotes": "Predição incorreta",
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK
        prediction.refresh_from_db()
        assert prediction.feedback is False
        assert prediction.feedback_notes == "Predição incorreta"

    def test_post_not_allowed(self, client):
        response = client.post(
            path="/MLPrediction/?company={}".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "MLPrediction",
                    "attributes": {"outputData": {}},
                }
            },
        )

        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_delete_not_allowed(self, client):
        prediction = MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": "test-rdo-1"},
        )

        response = client.delete(
            path="/MLPrediction/{}/".format(str(prediction.uuid)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_filter_by_feedback(self, client):
        MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": "rdo-1"},
            feedback=True,
        )
        MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": "rdo-2"},
            feedback=False,
        )
        MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": "rdo-3"},
        )

        response = client.get(
            path="/MLPrediction/?company={}&feedback=true".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert len(content["data"]) == 1

    def test_unauthenticated_returns_401(self, client):
        response = client.get(
            path="/MLPrediction/?company={}".format(str(self.company.pk)),
            content_type="application/vnd.api+json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
