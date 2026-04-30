import json

import pytest
from rest_framework import status

from apps.users.models import User, UserSignature
from helpers.testing.fixtures import TestBase

from ..models import MultipleDailyReport, MultipleDailyReportSignature

pytestmark = pytest.mark.django_db


class TestMultipleDailyReportSignature(TestBase):
    model = "MultipleDailyReportSignature"

    def test_multiple_daily_report_signature_list(self, client):
        """
        Ensures we can list using the MultipleDailyReport endpoint
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

    def test_multiple_daily_report_signature_without_company(self, client):
        """
        Ensures calling the MultipleDailyReportSignature endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_multiple_daily_report_signature(self, client):
        """
        Ensures a specific multiple daily report can be fetched using the uuid
        """

        report = MultipleDailyReportSignature.objects.filter(
            multiple_daily_report__company=self.company
        ).first()

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

    def test_create_multiple_daily_report_signature(self, client):
        """
        Ensures a new multiple daily report can be created using the endpoint
        """

        rdo = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "signature_name": "teste",
                        "md5": "",
                        "upload": {
                            "filename": "e8c01a27-ef71-4260-9fed-3356d9ff0f96.jpg"
                        },
                    },
                    "relationships": {
                        "multipleDailyReport": {
                            "data": {
                                "type": "MultipleDailyReport",
                                "id": str(rdo.pk),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

        content = json.loads(response.content)

        assert content["data"]["attributes"]["signatureName"] == "teste"

    def test_create_multiple_daily_report_signature_without_rdo(self, client):

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "signature_name": "teste",
                        "md5": "",
                        "upload": {
                            "filename": "f327e8a7-6e04-4909-be66-6866ed20abc0.jpg"
                        },
                    },
                    "relationships": {},
                }
            },
        )

        # Object was not created successfully
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_multiple_daily_report_signature_rdo_filter(self, client):

        rdo = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        response = client.get(
            path="/{}/?company={}&multiple_daily_report={}".format(
                self.model, str(self.company.pk), str(rdo.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 2

    def test_multiple_daily_report_signature_jobs_rdos_user_firms_filter(self, client):

        response = client.get(
            path="/{}/?company={}&rdos_user_firms=7".format(
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
        assert content["meta"]["pagination"]["count"] == 2

    def test_create_multiple_daily_report_no_photo(self, client):
        """
        Ensures a new multiple daily report can be created using the endpoint
        """

        rdo = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "signature_name": "teste",
                        "md5": "",
                        "upload": {
                            "filename": "e8c01a27-ef71-4260-9fed-3356d9ff0f96.pdf"
                        },
                    },
                    "relationships": {
                        "multipleDailyReport": {
                            "data": {
                                "type": "MultipleDailyReport",
                                "id": str(rdo.pk),
                            }
                        },
                    },
                }
            },
        )

        # Object was not created successfully
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        content = json.loads(response.content)

        expected_message = (
            "kartado.error.multiple_daily_report_signature.uploaded_file_is_not_a_photo"
        )
        assert content["errors"][0]["detail"] == expected_message

    def test_creating_new_user_signature(self, client):
        """
        User signature will be created since user doesn't have one
        """

        rdo = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        user = User.objects.filter(uuid="e7cfb4c3-ddd1-43e2-8439-c4c6f0a98383").first()

        response = client.post(
            path="/{}/".format(self.model),
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
                        "createUserSignature": {
                            "type": "UserSignature",
                            "uuid": "fc3d86be-b462-435a-9d06-8435e82fb286",
                            "user": {
                                "type": "User",
                                "id": str(user.pk),
                            },
                            "upload": {
                                "filename": "c3d86be-b462-435a-9d06-8435e82fb286.jpg"
                            },
                            "md5": "",
                        },
                    },
                    "relationships": {
                        "multipleDailyReport": {
                            "data": {
                                "type": "MultipleDailyReport",
                                "id": str(rdo.pk),
                            }
                        },
                    },
                }
            },
        )
        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

        # 2 in fixtures + 1 created in POST request
        assert UserSignature.objects.count() == 3

        content = json.loads(response.content)

        assert content["data"]["attributes"]["signatureName"] == user.get_full_name()

    def test_not_creating_new_user_signature(self, client):
        """
        User signature will not be created since user already has one in the company, but the request will be completed
        """

        rdo = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        user = User.objects.filter(uuid="4e29d1e0-9745-48d3-b38f-b1210e683e00").first()

        response = client.post(
            path="/{}/".format(self.model),
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
                        "createUserSignature": {
                            "type": "UserSignature",
                            "uuid": "fc3d86be-b462-435a-9d06-8435e82fb286",
                            "user": {
                                "type": "User",
                                "id": str(user.pk),
                            },
                            "upload": {
                                "filename": "c3d86be-b462-435a-9d06-8435e82fb286.jpg"
                            },
                            "md5": "",
                        },
                    },
                    "relationships": {
                        "multipleDailyReport": {
                            "data": {
                                "type": "MultipleDailyReport",
                                "id": str(rdo.pk),
                            }
                        },
                    },
                }
            },
        )
        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

        # 2 in fixtures
        assert UserSignature.objects.count() == 2

        content = json.loads(response.content)

        assert content["data"]["attributes"]["signatureName"] == user.get_full_name()

    def test_post_with_user_signature(self, client):
        rdo = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        signature = UserSignature.objects.first()
        user = signature.user

        response = client.post(
            path="/{}/".format(self.model),
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
                        "multipleDailyReport": {
                            "data": {
                                "type": "MultipleDailyReport",
                                "id": str(rdo.pk),
                            }
                        },
                        "userSignature": {
                            "data": {
                                "type": "UserSignature",
                                "id": str(signature.pk),
                            }
                        },
                    },
                }
            },
        )
        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

        # 2 in fixtures
        assert UserSignature.objects.count() == 2

        content = json.loads(response.content)

        assert content["data"]["attributes"]["signatureName"] == user.get_full_name()
