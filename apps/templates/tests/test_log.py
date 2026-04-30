import json
from datetime import datetime

import pytest
from rest_framework import status

from apps.templates.models import Log
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestLog(TestBase):
    model = "Log"

    def test_create_log_without_company(self, client):

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="",
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"date": datetime.now(), "description": {}},
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = Log.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_log_with_company(self, client):

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="",
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"date": datetime.now(), "description": {}},
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
        obj_created = Log.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED
