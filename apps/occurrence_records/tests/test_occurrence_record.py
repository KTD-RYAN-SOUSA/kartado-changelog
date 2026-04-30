import json
from unittest.mock import Mock, patch

import pytest
from django.contrib.gis.geos import GeometryCollection, Point, Polygon
from requests.models import Response
from rest_framework import status

from apps.companies.models import Company
from apps.maps.models import ShapeFile
from apps.occurrence_records.models import OccurrenceRecord, OccurrenceType
from apps.service_orders.models import ServiceOrderActionStatus
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestOccurrenceRecord(TestBase):
    model = "OccurrenceRecord"

    def test_list_occurrence_record(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_occurrence_record_without_queryset(self, client):
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

    def test_list_occurrence_record_without_company(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_filter_occurrence_record(self, client):
        action_status = ServiceOrderActionStatus.objects.filter(companies=self.company)[
            0
        ]

        response = client.get(
            path="/{}/?company={}&status={}".format(
                self.model, str(self.company.pk), str(action_status.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_occurrence_record(self, client):
        record = OccurrenceRecord.objects.filter(company=self.company)[0]

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(record.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_occurrence_record(self, client):
        occtype = OccurrenceType.objects.filter(company=self.company).first()
        del self.company.metadata["company_prefix"]
        del self.company.metadata["RO_name_format"]
        self.company.save()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occtype.pk),
                            }
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = OccurrenceRecord.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_occurrence_record_with_wrong_keyname(self, client):
        occtype = OccurrenceType.objects.filter(company=self.company).first()
        self.company.metadata["RO_name_format"] = "test"
        self.company.save()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occtype.pk),
                            }
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_update_occurrence_record(self, client):
        record = OccurrenceRecord.objects.filter(company=self.company, editable=True)[0]

        response = client.patch(
            path="/{}/{}/".format(self.model, str(record.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(record.pk),
                    "attributes": {"origin": "test"},
                    "relationships": {
                        "mainLinkedRecord": {
                            "data": {
                                "type": "OccurrenceRecord",
                                "id": "1521a932-86d1-4f60-bcc5-97682d303926",
                            }
                        },
                    },
                },
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_occurrence_record_main_linked_record(self, client):
        record = OccurrenceRecord.objects.filter(
            company=self.company, editable=True
        ).first()

        main_linked_record_new = str(
            OccurrenceRecord.objects.exclude(pk=record.pk).order_by("?").first().pk
        )

        response = client.patch(
            path="/{}/{}/".format(self.model, str(record.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(record.pk),
                    "attributes": {"origin": "test"},
                    "relationships": {
                        "mainLinkedRecord": {
                            "data": {
                                "type": "OccurrenceRecord",
                                "id": main_linked_record_new,
                            }
                        },
                    },
                },
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK
        assert response.data["main_linked_record"]["id"] == main_linked_record_new

    def test_delete_occurrence_record(self, client):
        record = OccurrenceRecord.objects.filter(company=self.company, editable=True)[0]

        response = client.delete(
            path="/{}/{}/".format(self.model, str(record.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_change_status_occurrence_record_sendtoapproval(self, client):
        record = OccurrenceRecord.objects.filter(company=self.company)[0]

        response = client.post(
            path="/{}/{}/{}/?company={}".format(
                self.model, str(record.pk), "ChangeStatus", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"action": "sendToApproval"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_change_status_occurrence_record_review(self, client):
        record = OccurrenceRecord.objects.filter(company=self.company)[0]

        response = client.post(
            path="/{}/{}/{}/?company={}".format(
                self.model, str(record.pk), "ChangeStatus", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"action": "requestReview"},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_change_status_occurrence_record_without_action(self, client):
        record = OccurrenceRecord.objects.filter(company=self.company)[0]

        response = client.post(
            path="/{}/{}/{}/?company={}".format(
                self.model, str(record.pk), "ChangeStatus", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": {"action": "test"}}},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_occurrence_record_geo(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "OccurrenceRecordGeo", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_occurrence_record_geo_without_queryset(self, client):
        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "OccurrenceRecordGeo", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        false_permission(self.user, self.company, self.model, allowed="self")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(
                "OccurrenceRecordGeo", str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_occurrence_record_geo(self, client):
        record = OccurrenceRecord.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                "OccurrenceRecordGeo", str(record.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_occurrence_record_geo_without_color(self, client):
        record = OccurrenceRecord.objects.filter(company=self.company).first()
        occtype = OccurrenceType.objects.create(name="test")
        record.occurrence_type = occtype
        record.save()

        response = client.get(
            path="/{}/{}/?company={}".format(
                "OccurrenceRecordGeo", str(record.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_occurrence_hydrology(self, client):
        response = client.get(
            path="/{}/{}/?company={}&datetime={}".format(
                "OccurrenceRecord",
                "GetHydrology",
                str(self.company.pk),
                "2020-11-23T13:26:00.000Z",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_occurrence_record_bi(self, client):
        response = client.get(
            path="/OccurrenceRecord/BI/?page_size=1",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_occurrence_record_bi_false(self, client):
        false_permission(self.user, self.company, self.model)

        response = client.get(
            path="/OccurrenceRecord/BI/?page_size=1",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_occurrence_record_filter_accepts_partial_range(self, client):
        """
        Ensures the correct behavior when querying with the form_data
        filter. Also makes sure that partial ranges work properly.
        """

        # Update the occurence record used for tests to have formData of "length" with value 10
        record = OccurrenceRecord.objects.filter(company=self.company, editable=True)[0]

        response = client.patch(
            path="/{}/{}/".format(self.model, str(record.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(record.pk),
                    "attributes": {"formData": {"length": 10}},
                }
            },
        )

        # Ensure the update went okay
        assert response.status_code == status.HTTP_200_OK

        def api_call_with_range(range):
            """
            Calls the OccurenceRecord endpoint with the provided form_data
            and returns the response data.
            """
            response = client.get(
                path="/{}/?company={}&form_data={}".format(
                    self.model, str(self.company.pk), range
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
                data={},
            )
            # response.data["results"][0]["form_data"]
            return response.data

        # From length 10 to 100 (inclusive)
        resp = api_call_with_range('{"length":{"from":10,"to":100}}')
        # Check it's one result
        assert resp["meta"]["pagination"]["count"] == 1
        # Ensure its length is the provided one
        assert resp["results"][0]["form_data"]["length"] == 10

        # Partial range from 10
        # Check the same result still appears with a partial "from" range
        resp = api_call_with_range('{"length":{"from":10}}')
        assert resp["meta"]["pagination"]["count"] == 1

        # Partial range to 100
        # Check the same result still appears with a partial "to" range
        resp = api_call_with_range('{"length":{"to":100}}')
        assert resp["meta"]["pagination"]["count"] == 1

    def test_filter_number_in_occurrence_record(self, client):
        instance_occurrence = (
            OccurrenceRecord.objects.filter(company=self.company.pk)
            .order_by("?")
            .first()
        )

        number = instance_occurrence.number

        response = client.get(
            path="/{}/?company={}&number={}".format(
                self.model, str(self.company.pk), number
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        search_valid = False

        for result in response.data["results"]:
            if number in result["number"]:
                search_valid = True
            else:
                search_valid = False
                break

        assert search_valid

    def test_get_occurrence_record_serializer_properties_in_geometry(self, client):
        record = OccurrenceRecord.objects.filter(
            properties__isnull=False, geometry__isnull=False, company=self.company
        ).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(record.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        assert (
            response.data["properties"][0]["elevation_m"]
            == record.properties[0]["elevation_m"]
        )

    def test_set_altimetry_success_with_one_coordinate(self):
        # Point( -51.8533, -15.3135 ) --> This point should return an altitude value of 285 meters

        with patch(
            "apps.occurrence_records.helpers.apis.tessadem.functions.requests"
        ) as mock_external_api:
            # Create request response
            request = Mock()
            request.body = None
            request.method = None
            request.url = None
            response = Response()
            response.request = request
            response.status_code = 200
            response.headers = None
            response._content = b'{"results": [{"elevation": 285}]}'
            mock_external_api.get.return_value = response

            # Enable altimetry for company
            self.company.metadata["altimetry_enable"] = True
            self.company.save()

            # When creating a record it goes through the set_altimetry method
            record = OccurrenceRecord.objects.create(
                company=self.company,
                created_by=self.user,
                geometry=GeometryCollection(Point(-51.8533, -15.3135)),
            )

            assert record.properties[0]["elevation_m"] == 285

    def test_set_altimetry_success_with_two_coordinates(self):
        # Point( -52.942022, -26.568681 ) --> This point should return an altitude value of 472 meters
        # Point( -52.93814, -26.567558 ) --> This point should return an altitude value of 498 meters

        with patch(
            "apps.occurrence_records.helpers.apis.tessadem.functions.requests"
        ) as mock_external_api:
            # Create request response
            request = Mock()
            request.body = None

            response1 = Response()
            response1.request = request
            response1.status_code = 200
            response1.headers = None
            response1._content = b'{"results": [{"elevation": 472}]}'

            response2 = Response()
            response2.request = request
            response2.status_code = 200
            response2.headers = None
            response2._content = b'{"results": [{"elevation": 498}]}'

            mock_external_api.get.side_effect = [response1, response2]

            # Enable altimetry for company
            self.company.metadata["altimetry_enable"] = True
            self.company.save()

            # When creating a record it goes through the set_altimetry method
            record = OccurrenceRecord.objects.create(
                company=self.company,
                created_by=self.user,
                geometry=GeometryCollection(
                    Point(-52.942022, -26.568681), Point(-52.93814, -26.567558)
                ),
            )

            # Check if the elevations are set correctly
            assert record.properties[0]["elevation_m"] == 472
            assert record.properties[1]["elevation_m"] == 498

    def test_occurrence_record_view_find_intersects(self, client):
        # Create a simple square polygon and a shapefile with same polygon to intersect
        square = Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)))
        shape = ShapeFile.objects.create(name="Props", created_by=self.user)
        shape.geometry = GeometryCollection(square)
        shape.properties = [{"OBJECTID": 1, "name": "A"}]
        shape.save()

        # Point company metadata to this shapefile
        company = Company.objects.get(pk=self.company.pk)
        company.metadata["properties_shape"] = str(shape.uuid)
        company.save(update_fields=["metadata"])

        feature_collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[0.5, 0.5], [0.5, 2], [2, 2], [2, 0.5], [0.5, 0.5]]
                        ],
                    },
                }
            ],
        }

        resp = client.post(
            path=f"/{self.model}/FindIntersects/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
            data=json.dumps(
                {
                    "data": {
                        "type": "OccurrenceRecord",
                        "attributes": {
                            "company": {"id": str(company.uuid)},
                            "feature_collection": feature_collection,
                        },
                    }
                }
            ),
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        intersects = data["data"]["data"]["intersects"]
        assert isinstance(intersects, list)
        assert len(intersects) == 1
        assert intersects[0]["attributes"]["uuid"].startswith(str(shape.uuid))

    def test_occurrence_record_view_find_intersects_missing_params(self, client):
        resp = client.post(
            path=f"/{self.model}/FindIntersects/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
            data=json.dumps({"data": {"type": "OccurrenceRecord", "attributes": {}}}),
        )
        assert resp.status_code == 400
