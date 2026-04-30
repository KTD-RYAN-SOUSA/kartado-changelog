import json

import pytest
from rest_framework import status

from apps.companies.models import Firm, InspectorInFirm
from apps.users.models import User
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestInspectorInFirm(TestBase):
    model = "InspectorInFirm"

    def test_list_inspectorinfirms(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_inspectorinfirms_without_queryset(self, client):

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

    def test_list_inspectorinfirms_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_inspectorinfirms_without_uuid(self, client):

        response = client.get(
            path="/{}/?company={}".format(self.model, "test"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_inspectorinfirm(self, client):

        firm = Firm.objects.filter(company=self.company).first()
        inspectors_in_firm = (
            InspectorInFirm.objects.all().values_list("user", flat=True).distinct()
        )
        user = User.objects.all().exclude(pk__in=inspectors_in_firm)[0]

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "user": {"data": {"type": "User", "id": str(user.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = InspectorInFirm.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_update_inspectorinfirm(self, client):

        inspector_in_firm = InspectorInFirm.objects.first()
        firm = Firm.objects.all().exclude(pk=inspector_in_firm.firm.pk).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(inspector_in_firm.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(inspector_in_firm.pk),
                    "relationships": {
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}}
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_200_OK
