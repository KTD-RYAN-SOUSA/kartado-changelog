import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase

from ..models import User, UserSignature

pytestmark = pytest.mark.django_db


class TestUserSignature(TestBase):
    model = "UserSignature"

    def test_user_signature_list(self, client):
        """
        Ensures we can list using the UserSignature endpoint
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
        assert content["meta"]["pagination"]["count"] == 2

    def test_user_signature_without_company(self, client):
        """
        Ensures calling the UserSignature endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_user_signature(self, client):
        """
        Ensures a specific user signature can be fetched using the uuid
        """
        report = UserSignature.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(report.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_user_signature(self, client):
        """
        Ensures a new user signature can be created using the endpoint
        """

        user = User.objects.filter(uuid="e7cfb4c3-ddd1-43e2-8439-c4c6f0a98383").first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "md5": "",
                        "upload": {
                            "filename": "e8c01a27-ef71-4260-9fed-3356d9ff0f96.jpg"
                        },
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "user": {
                            "data": {
                                "type": "User",
                                "id": str(user.pk),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_user_signature_user_filter(self, client):

        user = User.objects.filter(uuid="0aa50773-b368-4a50-9f12-4a7d8dfaf256").first()

        response = client.get(
            path="/{}/?company={}&user={}".format(
                self.model, str(self.company.pk), str(user.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 1

    def test_user_signature_created_at_filter(self, client):

        response = client.get(
            path="/{}/?company={}&created_at_after=2025-08-01".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 1

    def test_create_user_signature_no_photo(self, client):
        """
        Ensures a new user signature cannot be created if it's not a photo
        """

        user = User.objects.filter(uuid="e7cfb4c3-ddd1-43e2-8439-c4c6f0a98383").first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "md5": "",
                        "upload": {
                            "filename": "e8c01a27-ef71-4260-9fed-3356d9ff0f96.pdf"
                        },
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "user": {
                            "data": {
                                "type": "User",
                                "id": str(user.pk),
                            }
                        },
                    },
                }
            },
        )
        # Object was not created successfully
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        content = json.loads(response.content)

        expected_message = "kartado.error.user_signature.uploaded_file_is_not_a_photo"
        assert content["errors"][0]["detail"] == expected_message

    def test_user_signature_unique_together(self, client):
        """
        Ensures a new user signature cannot be created if user+company is repeated
        """

        user = User.objects.filter(uuid="4e29d1e0-9745-48d3-b38f-b1210e683e00").first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "md5": "",
                        "upload": {
                            "filename": "e8c01a27-ef71-4260-9fed-3356d9ff0f96.jpg"
                        },
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "user": {
                            "data": {
                                "type": "User",
                                "id": str(user.pk),
                            }
                        },
                    },
                }
            },
        )
        # Object was not created successfully
        assert response.status_code == status.HTTP_400_BAD_REQUEST
