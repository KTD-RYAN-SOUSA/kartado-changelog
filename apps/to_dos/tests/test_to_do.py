from datetime import datetime

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase, false_permission

from ..models import ToDo, ToDoAction

pytestmark = pytest.mark.django_db


class TestToDo(TestBase):
    model = "ToDo"

    def test_to_do_list(self, client):
        """
        Ensures we can list using the ToDo endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

    def test_get_to_do(self, client):
        """
        Ensures a specific ToDo can be fetched using the uuid
        """

        instance = ToDo.objects.filter(company=self.company).first()

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

    def test_create_to_do(self, client):
        """
        Ensures a new ToDo can be created using the endpoint
        """

        to_do_action = ToDoAction.objects.first()

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
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
                        "action": {
                            "data": {
                                "type": "ToDoAction",
                                "id": str(to_do_action.pk),
                            }
                        },
                        "responsibles": {
                            "data": [{"type": "User", "id": str(self.user.pk)}]
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_to_do_without_company_id(self, client):
        """
        Ensures a new ToDo cannot be created
        without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"destination": "NEW TEST"},
                }
            },
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_to_do_without_permission(self, client):
        """
        Ensures a new ToDo cannot be created without
        the proper permissions
        """

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"destination": "NEW TEST"},
                }
            },
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_to_do(self, client):  # TODO: changge
        """
        Ensure a ToDo can be updated using the endpoint
        """

        instance = ToDo.objects.first()

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
                    "attributes": {"destination": "NEW TEST"},
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_to_do(self, client):
        """
        Ensure a ToDo can be deleted using the endpoint
        """

        instance = ToDo.objects.first()

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

    def test_to_do_filter_is_read_true(self, client):
        """
        Ensures we can list using the ToDo endpoint
        and the fixture is properly listed
        """

        is_read = True

        response = client.get(
            path="/{}/?company={}&is_read={}&page_size=1".format(
                self.model, str(self.company.pk), is_read
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        qs = ToDo.objects.filter(company=self.company, read_at__isnull=not is_read)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] == qs.count()

    def test_to_do_filter_is_read_false(self, client):
        """
        Ensures we can list using the ToDo endpoint
        and the fixture is properly listed
        """

        is_read = False

        response = client.get(
            path="/{}/?company={}&is_read={}&page_size=1".format(
                self.model, str(self.company.pk), is_read
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        qs = ToDo.objects.filter(company=self.company, read_at=None)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] == qs.count()

    def test_update_to_do_set_read_at(self, client):
        """
        Ensure a ToDo can be updated set read_at using the endpoint
        """

        instance = ToDo.objects.first()
        date_time_set = str(datetime.now())

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
                    "attributes": {"read_at": date_time_set},
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

        input_datetime = response.data["read_at"]
        input_datetime_without_timezone = input_datetime[:-6]

        datetime_object = datetime.fromisoformat(input_datetime_without_timezone)
        formatted_datetime = datetime_object.strftime("%Y-%m-%d %H:%M:%S.%f")

        assert formatted_datetime == date_time_set

    def test_update_to_do_set_read_at_response_is_done_true(self, client):
        """
        Ensure a ToDo can be updated set read_at response is_done true using the endpoint
        """

        instance = ToDo.objects.filter(
            company=self.company, read_at=None, action__default_options="see"
        ).first()

        date_time_set = str(datetime.now())

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
                    "attributes": {"read_at": date_time_set},
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

        assert response.data["is_done"] is True

    def test_update_to_do_clean_read_at_response_is_done_false(self, client):
        """
        Ensure a ToDo can be updated set read_at response is_done true using the endpoint
        """

        instance = ToDo.objects.filter(
            company=self.company, read_at__isnull=False, action__default_options="see"
        ).first()

        date_time_set = None

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
                    "attributes": {"read_at": date_time_set},
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

        assert response.data["is_done"] is False

    def test_to_do_bulk_read_set_read_true(self, client):
        """
        Ensures we can list using the ToDo endpoint
        and the fixture is properly listed
        """
        queryset = ToDo.objects.filter(read_at=None)
        read = True

        response = client.patch(
            path="/{}/BulkRead/?company={}&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"to_dos": list(queryset.values_list("pk", flat=True)), "read": read},
        )
        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        response_is_valid = True
        for content in response.data:
            if not content["read_at"]:
                response_is_valid = False
                break

        assert response_is_valid is True

    def test_to_do_bulk_read_set_read_false(self, client):
        """
        Ensures we can list using the ToDo endpoint
        and the fixture is properly listed
        """
        queryset = ToDo.objects.filter(read_at__isnull=False)

        read = False

        response = client.patch(
            path="/{}/BulkRead/?company={}&page_size=1".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"to_dos": list(queryset.values_list("pk", flat=True)), "read": read},
        )
        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        response_is_valid = True
        for content in response.data:
            if content["read_at"]:
                response_is_valid = False
                break

        assert response_is_valid is True

    def test_check_field_see(self, client):
        """
        Ensures a specific ToDo can be fetched using the uuid
        """
        instance = ToDo.objects.filter(company=self.company).first()
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
        assert response.data["see"] is not None
