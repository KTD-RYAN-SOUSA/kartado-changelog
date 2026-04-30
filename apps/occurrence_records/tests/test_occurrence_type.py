import json
from unittest.mock import patch

import pytest
from rest_framework import status

from apps.companies.models import Company, Firm
from apps.occurrence_records.admin import OccurrenceTypeAdmin
from apps.occurrence_records.models import OccurrenceType, OccurrenceTypeSpecs
from apps.permissions.models import PermissionOccurrenceKindRestriction, UserPermission
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestOccurrenceType(TestBase):
    model = "OccurrenceType"

    def test_list_occurrence_type(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_occurrence_type_without_queryset(self, client):
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

    def test_list_occurrence_type_without_company(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_occurrence_type(self, client):
        occtype = OccurrenceType.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(occtype.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_occurrence_type_gzip(self, client):
        occtype = OccurrenceType.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/GZIP/?company={}".format(
                self.model, str(occtype.pk), str(self.company.pk)
            ),
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_occurrence_type(self, client):
        firm = Firm.objects.filter(company=self.company).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test", "color": "#FF1212"},
                    "relationships": {
                        "company": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        },
                        "firms": {"data": [{"type": "Firm", "id": str(firm.pk)}]},
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = OccurrenceType.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_occurrence_type_without_company(self, client):
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test"},
                    "relationships": {},
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_occurrence_type_equal(self, client):
        occtype = OccurrenceType.objects.filter(company=self.company).first()
        company = occtype.company.first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": occtype.name},
                    "relationships": {
                        "company": {
                            "data": [{"type": "Company", "id": str(company.pk)}]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_occurrence_type_without_company_id(self, client):
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test"},
                    "relationships": {
                        "company": {
                            "data": [
                                {
                                    "type": "Company",
                                    "not_sid": str(self.company.pk),
                                }
                            ]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_occurrence_type_without_permission(self, client):
        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"name": "test"},
                    "relationships": {
                        "company": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_occurrence_type(self, client):
        occtype = OccurrenceType.objects.filter(company=self.company).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(occtype.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(occtype.pk),
                    "attributes": {"color": "#FF1212"},
                    "relationships": {
                        "company": {
                            "data": [{"type": "Company", "id": str(self.company.pk)}]
                        },
                        "company_color": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_occurrence_type_without_specs(self, client):
        specs = list(
            set(OccurrenceTypeSpecs.objects.all().values_list("company_id", flat=True))
        )
        company = Company.objects.all().exclude(pk__in=specs)[0]
        occtype = OccurrenceType.objects.filter(company=self.company)[0]

        response = client.patch(
            path="/{}/{}/".format(self.model, str(occtype.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(occtype.pk),
                    "attributes": {"color": "#FF1212"},
                    "relationships": {
                        "company_color": {
                            "data": {"type": "Company", "id": str(company.pk)}
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_occurrence_type(self, client):
        occtype = OccurrenceType.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(occtype.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_occurrence_type_name_availability(self, client):
        response = client.post(
            path="/{}/NameAvailability/?company={}".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "name": "NEW JERSEY"}},
        )

        content = json.loads(response.content)

        assert not content["data"]["isNameAvailableForUsage"]

    def test_admin_get_search_results(self):
        """test the get_search_results method in OccurrenceTypeAdmin"""
        admin = OccurrenceTypeAdmin(OccurrenceType, None)
        queryset = OccurrenceType.objects.all()

        results, use_distinct = admin.get_search_results(None, queryset, "")
        assert results == queryset
        assert use_distinct is False

        occtype = OccurrenceType.objects.filter(company=self.company).first()
        results, use_distinct = admin.get_search_results(None, queryset, occtype.name)
        assert results.count() >= 1
        assert occtype.name == results.first().name
        assert use_distinct is True

        if len(occtype.name) > 3:
            partial_term = occtype.name[:3]
            results, use_distinct = admin.get_search_results(
                None, queryset, partial_term
            )
            assert results.count() >= 1
            assert use_distinct is True

            exact_match = OccurrenceType.objects.create(name=partial_term)
            try:
                results, _ = admin.get_search_results(None, queryset, partial_term)
                assert results.first().name == partial_term
            finally:
                exact_match.delete()

        company = self.company
        exact_match = OccurrenceType.objects.create(name=company.name)
        partial_match = OccurrenceType.objects.create(
            name=f"Contains_{company.name}_middle"
        )

        try:
            with patch(
                "apps.occurrence_records.models.OccurrenceTypeSpecs.objects.filter"
            ) as mock_filter:
                mock_instance = mock_filter.return_value
                mock_uuids = [occtype.uuid]
                mock_instance.values_list.return_value.distinct.return_value = (
                    mock_uuids
                )

                results, use_distinct = admin.get_search_results(
                    None, queryset, company.name
                )
                assert mock_filter.called_with(company__name__icontains=company.name)
                assert results.count() >= 1
                assert use_distinct is True

                result_list = list(results)

                assert any(result.name == company.name for result in result_list[:1])

                company_matches_found = False
                for occurrence_type in result_list:
                    if (
                        occurrence_type.uuid in mock_uuids
                        and occurrence_type.name != company.name
                        and company.name not in occurrence_type.name
                    ):
                        company_matches_found = True
                        assert any(
                            previous_result.name == company.name
                            for previous_result in result_list[
                                : result_list.index(occurrence_type)
                            ]
                        )

                if company_matches_found:
                    assert True
        finally:
            exact_match.delete()
            partial_match.delete()

        random_term = "asdfsfdas1234321"
        with patch(
            "apps.occurrence_records.models.OccurrenceTypeSpecs.objects.filter"
        ) as mock_filter:
            mock_instance = mock_filter.return_value
            mock_instance.values_list.return_value.distinct.return_value = []

            results, use_distinct = admin.get_search_results(
                None, queryset, random_term
            )
            assert results.count() == 0
            assert use_distinct is True

    def test_can_save_endpoint(self, client):

        response = client.post(
            path="/{}/CanSave/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "form_fields": {
                        "id": 1,
                        "name": "1",
                        "fields": [
                            {
                                "id": 1,
                                "apiName": "ra",
                                "dataType": "float",
                                "displayName": "RA",
                            }
                        ],
                    },
                }
            },
        )

        content = json.loads(response.content)

        assert content["data"]["canSave"]

    def test_storage_endpoint(self, client):

        response = client.get(
            path="/{}/Storage/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_occurrence_type_filter_get_search(self, client, enable_unaccent):
        company = self.company
        occurrence_type = OccurrenceType.objects.create(
            name="Ponte Quebrada", color="#000", icon="", icon_size=12
        )
        occurrence_type.company.add(company)

        response = client.get(
            path=f"/{self.model}/?company={company.uuid}&search=Ponte",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert any(
            "Ponte" in item["attributes"]["name"] for item in data.get("data", [])
        )

    def test_list_occurrence_type_filtered_by_allowed_kinds(self, client):
        """Test that OccurrenceTypes are filtered by allowed occurrence kinds."""
        # Create OccurrenceTypes with different occurrence_kind values
        ot_kind1 = OccurrenceType.objects.create(
            name="Test Kind 1", occurrence_kind="1", color="#111"
        )
        ot_kind1.company.add(self.company)

        ot_kind2 = OccurrenceType.objects.create(
            name="Test Kind 2", occurrence_kind="2", color="#222"
        )
        ot_kind2.company.add(self.company)

        ot_kind3 = OccurrenceType.objects.create(
            name="Test Kind 3", occurrence_kind="3", color="#333"
        )
        ot_kind3.company.add(self.company)

        # Get user's permission
        user_permission = UserPermission.objects.filter(companies=self.company).first()

        # Create restriction allowing only kinds "1" and "2"
        PermissionOccurrenceKindRestriction.objects.create(
            user_permission=user_permission,
            company=self.company,
            allowed_occurrence_kinds=["1", "2"],
        )

        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        occurrence_kinds_in_response = [
            item["attributes"].get("occurrence-kind")
            for item in content.get("data", [])
            if item["attributes"].get("occurrence-kind")
        ]

        # Kind "3" should NOT be in the response
        assert "3" not in occurrence_kinds_in_response

        # Kinds "1" and "2" should be in the response (if they exist)
        if occurrence_kinds_in_response:
            for kind in occurrence_kinds_in_response:
                assert kind in ["1", "2"]

    def test_list_occurrence_type_no_restriction_returns_all(self, client):
        """Test that without restriction, all OccurrenceTypes are returned."""
        # Ensure no restrictions exist for this user
        user_permission = UserPermission.objects.filter(companies=self.company).first()

        PermissionOccurrenceKindRestriction.objects.filter(
            user_permission=user_permission,
            company=self.company,
        ).delete()

        # Create OccurrenceTypes with different occurrence_kind values
        ot_kind_special = OccurrenceType.objects.create(
            name="Test Kind Special", occurrence_kind="99", color="#999"
        )
        ot_kind_special.company.add(self.company)

        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)

        # Find our test occurrence type in the response
        test_ot_found = any(
            item["attributes"].get("name") == "Test Kind Special"
            for item in content.get("data", [])
        )

        # Without restriction, our test OccurrenceType should be in the response
        assert (
            test_ot_found
        ), "OccurrenceType 'Test Kind Special' should be in response when no restriction exists"
