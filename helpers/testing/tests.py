import json
from typing import Any, Dict, List, Tuple, Union
from uuid import UUID

import pytest
from django.db.models import Model
from rest_framework import status

from apps.companies.models import Company
from apps.users.models import User
from helpers.testing.fixtures import false_permission


@pytest.mark.urls("RoadLabsAPI.urls.base")
class BaseModelTests(object):
    """
    Meant to be inherited to automatically create the essential tests for a certain
    `model_class` provided that the subclass properly sets the manual fields.

    The fields and methods can also aid in simplifying other, more specific, personalized tests.

    IMPORTANT: The subclass should always override the `BaseModelTests.init_manual_fields` method.
    Check the method's docstring for more details.

    IMPORTANT: In case of a problem or a specific requirement of your model,
    you can always override specific tests defined here to account for differences.

    Methods with _ prefix are not meant to be used outside of this class.
    """

    # Automatic fields
    user: User
    company: Company
    token: str
    model_name: str

    # Manual fields
    model_class: Union[Model, None] = None
    model_attributes: Dict[str, Any] = {}
    update_attributes: Dict[str, Any] = {}
    model_relationships: Dict[str, Union[Model, List[Model]]] = {}

    def init_manual_fields(self):
        """
        Initialize the manual required fields to make the free automatic tests
        possible. See the example for usage.

        Manual fields:
            `model_class`: Receives the class of the model you're going to test.

            `model_attributes`: The necessary attributes to successfully create an instance of that model.

            `update_attributes`: Which attributes are going to be updated on the PATCH tests.

            `model_relationships`: The necessary relationships to sucessfully create an instance of that model.
            IMPORTANT: The `str` key should be the name of that relationship's field on the model,
            the value should be the instance.

        Raises:
            NotImplementedError: Raised when the method was not overriden on
            the child class.

        Example:
            ```python
            class TestDailyReportWorker(BaseModelTests):
                def init_manual_fields(self):
                    self.model_class = DailyReportWorker
                    self.model_attributes = {
                        "members": TYPE_SAMPLES[str],
                        "amount": TYPE_SAMPLES[int],
                        "role": TYPE_SAMPLES[str],
                    }
                    self.update_attributes = {
                        "amount": TYPE_SAMPLES[int] + 1,
                    }
                    self.model_relationships = {
                        "company": self.company,
                        "firm": DailyReportWorker.objects.first().firm,
                    }
            ```
        """
        raise NotImplementedError(
            "You are required to implement the setup_manual_fields method and fill the manual fields"
        )

    def _validate_manual_fields(self):
        """
        Validation of the provided manual fields.

        Raises:
            AssertionError: Will be raised if there was a problem with the provided
            manual fields.
        """

        assert issubclass(
            self.model_class, Model
        ), "Please provide a valid model_class for the tests"
        assert self.model_attributes, "Please provide proper model_attributes"
        assert self.model_relationships, "Please provide proper model_relationships"
        assert (
            self.update_attributes
        ), "Please provide at least one attribute to be updated on update_attributes"

    @pytest.fixture(autouse=True)
    def _initial(self, initial_data: Tuple[User, Company, str]):
        """
        Prepares all the data needed for the tests.

        Args:
            initial_data (Tuple[User, Company, str]): Automatic user, company and token
            data meant to feed the automatic fields and provide common important instances.
        """

        # Use initial data
        self.user, self.company, self.token = initial_data

        # Handle manual fields
        self.init_manual_fields()
        self._validate_manual_fields()
        self.model_name = self.model_class.__name__

        # Add the permissions (optional override when API checks another model)
        permission_model = (
            getattr(self, "permission_model_name", None) or self.model_name
        )
        false_permission(self.user, self.company, permission_model, all_true=True)

    def get_req_args(self, path: str, data: dict = {}) -> Dict[str, Any]:
        """
        Helper to easily build the request's arguments by providing a common
        boilerplate.

        Args:
            path (str): The API path that's going to be requested.
            data (dict, optional): The body that's going to be sent. Defaults to {}.

        Returns:
            Dict[str, Any]: The `**kwargs` for the client method calls.
            IMPORTANT: remember to use `**` on the response.

        Examples:
            ```python
            # Without data
            path = f"/{self.model_name}/"
            response = client.get(**self.get_req_args(path))

            # With data
            path = f"/{self.model_name}/"
            req_data = self.get_req_body()
            response = client.post(**self.get_req_args(path, data=req_data))
            ```
        """
        return {
            "path": path,
            "content_type": "application/vnd.api+json",
            "HTTP_AUTHORIZATION": f"JWT {self.token}",
            "data": data,
        }

    def _model_rel_to_req_body_rel(
        self, relationships: dict = {}
    ) -> Dict[str, Dict[str, Union[Dict[str, str], List[Dict[str, str]]]]]:
        """
        Converts the developer friendly structure of model_relationships
        (or the provided argument dict) to a request compatible version.

        Args:
            relationships (dict, optional): You can provide a different value instead of model_relatioships.
            Defaults to `model_relationships`.

        Raises:
            ValueError: Raised when the provided relationship dict has invalid
            type or incorrect structure.

        Returns:
            Dict[str, Dict[str, Union[Dict[str, str], List[Dict[str, str]]]]]: The
            request friendly relationships values.

        Example: See `BaseModelTests.get_req_body()`.
        """
        model_relationships = (
            relationships if relationships else self.model_relationships
        )
        body_relationships = {}

        for field_name, field_data in model_relationships.items():
            body_field_data = None

            if isinstance(field_data, list):
                body_field_data = [
                    {"type": type(instance).__name__, "id": str(instance.pk)}
                    for instance in field_data
                    if isinstance(instance, Model)
                ]
                if len(body_field_data) != len(field_data):
                    raise ValueError(
                        "Invalid list structure of field_data was provided to the model_relationships"
                    )
            elif isinstance(field_data, Model):
                body_field_data = {
                    "type": type(field_data).__name__,
                    "id": str(field_data.pk),
                }
            else:
                raise ValueError(
                    "Invalid type of field_data was provided to the model_relationships"
                )

            body_relationships[field_name] = {"data": body_field_data}

        return body_relationships

    def get_req_body(
        self,
        attributes: dict = {},
        relationships: dict = {},
        omit_relationships: bool = False,
        object_id: Union[UUID, str, None] = None,
    ) -> Dict[str, Dict[str, Union[str, dict]]]:
        """
        Build a request body according to either the initially provided manual fields
        or the arguments.

        Args:
            attributes (dict, optional): In case you need to provide different attributes than the `model_attributes`.
            Defaults to `model_attributes`.

            relationships (dict, optional): In case you need to provide different relationships than the `model_relationships`.
            Defaults to `model_attributes` if `omit_relationships` is False, `{}` if `omit_relationships` is True.

            object_id (Union[UUID, str, None], optional): Include the instance's ID in the body. Defaults to None.

            omit_relationships (bool, optional): If the relatioships should be sent as an empty dict. Defaults to False.

        Returns:
            Dict[str, Dict[str, Union[str, dict]]]: Final request body with type,
            attributes and relationships.
        """

        body_attributes = attributes or self.model_attributes
        body_relationships = (
            self._model_rel_to_req_body_rel(relationships)
            if not omit_relationships
            else {}
        )

        request_body = {
            "data": {
                "type": self.model_name,
                "attributes": body_attributes,
                "relationships": body_relationships,
            }
        }
        if object_id:
            request_body["data"]["id"] = str(object_id)

        return request_body

    # Default tests
    def test_model_lists_fixtures(self, client):
        """Make sure the model fixtures are properly returned on a GET request"""

        path = f"/{self.model_name}/?company={self.company.pk}"
        response = client.get(**self.get_req_args(path))
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] > 0

    def test_model_get_request_without_company_is_forbidden(self, client):
        """Ensure the GET request without providing a `company` is forbidden"""

        path = f"/{self.model_name}/"
        response = client.get(**self.get_req_args(path))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_model_get_id(self, client):
        """Ensure the GET on a specific instance is possible"""

        model_instance: Model = self.model_class.objects.first()
        path = f"/{self.model_name}/{model_instance.pk}/?company={self.company.pk}"
        response = client.get(**self.get_req_args(path))

        assert response.status_code == status.HTTP_200_OK

    def test_model_create(self, client):
        """
        Given the provided manual fields, make sure is possible to create a new
        instance with POST.
        """

        path = f"/{self.model_name}/"
        req_data = self.get_req_body()
        response = client.post(**self.get_req_args(path, data=req_data))

        assert response.status_code == status.HTTP_201_CREATED

    def test_model_create_without_permission_is_forbidden(self, client):
        """
        Make sure it's not possible to create an instance of the model without
        the proper permissions.
        """

        path = f"/{self.model_name}/"
        req_data = self.get_req_body()
        permission_model = (
            getattr(self, "permission_model_name", None) or self.model_name
        )
        false_permission(self.user, self.company, permission_model)
        response = client.post(**self.get_req_args(path, data=req_data))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_model_post_without_company_id_rel_is_forbidden(self, client):
        """
        Make sure not providing a path to the `Company` relationship
        results in a forbidden request.

        IMPORTANT: This does NOT mean not providing a direct relationship
        to `Company` (that happens in some models), it means that there is
        no direct relationship leading to the `Company` relationship.

        See your model's `get_company_id` to see how your particular model
        gets to a `Company` instance.
        """

        path = f"/{self.model_name}/"
        req_data = self.get_req_body(omit_relationships=True)
        response = client.post(**self.get_req_args(path, data=req_data))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_model_patch_update(self, client):
        """
        Ensure that a PATCH to update certain attributes is possible given
        the provided `update_attributes`.
        """

        model_instance: Model = self.model_class.objects.first()
        path = f"/{self.model_name}/{model_instance.pk}/?company={self.company.pk}"
        req_data = self.get_req_body(
            object_id=model_instance.pk, attributes=self.update_attributes
        )
        response = client.patch(**self.get_req_args(path, data=req_data))

        assert response.status_code == status.HTTP_200_OK

    def test_model_delete_id(self, client):
        """Make sure you can DELETE an instance of that model"""

        model_instance: Model = self.model_class.objects.first()
        path = f"/{self.model_name}/{model_instance.pk}/?company={self.company.pk}"
        response = client.delete(**self.get_req_args(path))

        assert response.status_code == status.HTTP_204_NO_CONTENT
