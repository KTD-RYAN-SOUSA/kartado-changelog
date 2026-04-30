import pytest
from rest_framework import status

from apps.companies.models import Company, CompanyGroup
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestCompanyGroup(TestBase):
    model = "CompanyGroup"

    def test_get_queryset_without_company_param(self, client):
        response = client.get(
            path="/{}/?page_size=1".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        content = response.json()
        assert content["meta"]["pagination"]["count"] == 0

    def test_get_queryset_with_company_param(self, client):
        new_company = Company.objects.create(
            name="New Test Company", cnpj="12.345.678/0001-99"
        )
        company_group = CompanyGroup.objects.create(
            name="Test Group", key_user=self.user
        )

        new_company.company_group = company_group
        new_company.save()

        response = client.get(
            path="/{}/?company={}".format(self.model, str(new_company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        content = response.json()

        assert content["meta"]["pagination"]["count"] == 1
        assert content["data"][0]["id"] == str(company_group.pk)

    def test_get_queryset_with_company_not_in_any_group(self, client):
        orphan_company = Company.objects.create(
            name="Orphan Company", cnpj="98.765.432/0001-11"
        )

        CompanyGroup.objects.create(name="Other Group", key_user=self.user)

        response = client.get(
            path="/{}/?company={}".format(self.model, str(orphan_company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        content = response.json()

        assert content["meta"]["pagination"]["count"] == 0

    def test_get_queryset_with_multiple_groups(self, client):
        company1 = Company.objects.create(name="Company 1", cnpj="11.111.111/0001-11")
        company2 = Company.objects.create(name="Company 2", cnpj="22.222.222/0001-22")

        group1 = CompanyGroup.objects.create(name="Group 1", key_user=self.user)
        group2 = CompanyGroup.objects.create(name="Group 2", key_user=self.user)

        company1.company_group = group1
        company1.save()

        company2.company_group = group2
        company2.save()

        response = client.get(
            path="/{}/?company={}".format(self.model, str(company1.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        content = response.json()

        assert content["meta"]["pagination"]["count"] == 1
        assert content["data"][0]["id"] == str(group1.pk)

    def test_get_queryset_with_fixture_company(self, client):
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        content = response.json()

        assert content["meta"]["pagination"]["count"] == 1
        fixture_group = self.company.company_group
        assert fixture_group is not None
        assert content["data"][0]["id"] == str(fixture_group.pk)
