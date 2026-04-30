import uuid
from unittest.mock import Mock

import pytest
from rest_framework import status

from apps.approval_flows.models import ApprovalFlow, ApprovalStep, ApprovalTransition
from apps.approval_flows.permissions import (
    ApprovalStepPermissions,
    ApprovalTransitionPermissions,
)
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestApprovalStepPermissions(TestBase):
    model = "ApprovalStep"

    @pytest.fixture(autouse=True)
    def setup_approval_step_data(self, _initial):
        # Create an approval flow for testing
        self.approval_flow = ApprovalFlow.objects.create(
            name="Test Approval Flow", target_model="TestModel", company=self.company
        )
        # Create an approval step for testing
        self.approval_step = ApprovalStep.objects.create(
            name="Test Step", approval_flow=self.approval_flow
        )

    def test_get_company_id_list_with_valid_company(self, client):
        """Test get_company_id for list action with valid company parameter"""
        permissions = ApprovalStepPermissions()
        request = Mock()
        request.query_params = {"company": str(self.company.pk)}

        result = permissions.get_company_id("list", request)

        assert result == self.company.pk

    def test_get_company_id_list_without_company_param(self, client):
        """Test get_company_id for list action without company parameter"""
        permissions = ApprovalStepPermissions()
        request = Mock()
        request.query_params = {}

        result = permissions.get_company_id("list", request)

        assert result is False

    def test_get_company_id_list_with_invalid_uuid(self, client):
        """Test get_company_id for list action with invalid UUID"""
        permissions = ApprovalStepPermissions()
        request = Mock()
        request.query_params = {"company": "invalid-uuid"}

        result = permissions.get_company_id("list", request)

        assert result is False

    def test_get_company_id_retrieve_with_valid_company(self, client):
        """Test get_company_id for retrieve action with valid company parameter"""
        permissions = ApprovalStepPermissions()
        request = Mock()
        request.query_params = {"company": str(self.company.pk)}

        result = permissions.get_company_id("retrieve", request)

        assert result == self.company.pk

    def test_get_company_id_create_with_valid_approval_flow(self, client):
        """Test get_company_id for create action with valid approval flow"""
        permissions = ApprovalStepPermissions()
        request = Mock()
        request.data = {"approval_flow": {"id": str(self.approval_flow.pk)}}

        result = permissions.get_company_id("create", request)

        assert result == self.company.pk

    def test_get_company_id_create_with_invalid_approval_flow(self, client):
        """Test get_company_id for create action with invalid approval flow"""
        permissions = ApprovalStepPermissions()
        request = Mock()
        request.data = {"approval_flow": {"id": str(uuid.uuid4())}}

        result = permissions.get_company_id("create", request)

        assert result is False

    def test_get_company_id_create_with_missing_approval_flow(self, client):
        """Test get_company_id for create action with missing approval flow"""
        permissions = ApprovalStepPermissions()
        request = Mock()
        request.data = {}

        result = permissions.get_company_id("create", request)

        assert result is False

    def test_get_company_id_update_with_valid_object(self, client):
        """Test get_company_id for update action with valid object"""
        permissions = ApprovalStepPermissions()
        request = Mock()

        result = permissions.get_company_id("update", request, self.approval_step)

        assert result == self.company.pk

    def test_get_company_id_partial_update_with_valid_object(self, client):
        """Test get_company_id for partial_update action with valid object"""
        permissions = ApprovalStepPermissions()
        request = Mock()

        result = permissions.get_company_id(
            "partial_update", request, self.approval_step
        )

        assert result == self.company.pk

    def test_get_company_id_destroy_with_valid_object(self, client):
        """Test get_company_id for destroy action with valid object"""
        permissions = ApprovalStepPermissions()
        request = Mock()

        result = permissions.get_company_id("destroy", request, self.approval_step)

        assert result == self.company.pk

    def test_get_company_id_unknown_action(self, client):
        """Test get_company_id for unknown action"""
        permissions = ApprovalStepPermissions()
        request = Mock()

        result = permissions.get_company_id("unknown_action", request)

        assert result is False

    def test_approval_step_list_with_company_param(self, client):
        """Test list endpoint with company parameter"""
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK

    def test_approval_step_list_without_company_param(self, client):
        """Test list endpoint without company parameter"""
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_approval_step_retrieve_with_company_param(self, client):
        """Test retrieve endpoint with company parameter"""
        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(self.approval_step.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK

    def test_approval_step_retrieve_without_company_param(self, client):
        """Test retrieve endpoint without company parameter"""
        response = client.get(
            path="/{}/{}/".format(self.model, str(self.approval_step.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestApprovalTransitionPermissions(TestBase):
    model = "ApprovalTransition"

    @pytest.fixture(autouse=True)
    def setup_approval_transition_data(self, _initial):
        # Create an approval flow for testing
        self.approval_flow = ApprovalFlow.objects.create(
            name="Test Approval Flow", target_model="TestModel", company=self.company
        )
        # Create approval steps for testing
        self.origin_step = ApprovalStep.objects.create(
            name="Origin Step", approval_flow=self.approval_flow
        )
        self.destination_step = ApprovalStep.objects.create(
            name="Destination Step", approval_flow=self.approval_flow
        )
        # Create an approval transition for testing
        self.approval_transition = ApprovalTransition.objects.create(
            name="Test Transition",
            origin=self.origin_step,
            destination=self.destination_step,
        )

    def test_get_company_id_list_with_valid_company(self, client):
        """Test get_company_id for list action with valid company parameter"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()
        request.query_params = {"company": str(self.company.pk)}

        result = permissions.get_company_id("list", request)

        assert result == self.company.pk

    def test_get_company_id_list_without_company_param(self, client):
        """Test get_company_id for list action without company parameter"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()
        request.query_params = {}

        result = permissions.get_company_id("list", request)

        assert result is False

    def test_get_company_id_list_with_invalid_uuid(self, client):
        """Test get_company_id for list action with invalid UUID"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()
        request.query_params = {"company": "invalid-uuid"}

        result = permissions.get_company_id("list", request)

        assert result is False

    def test_get_company_id_retrieve_with_valid_company(self, client):
        """Test get_company_id for retrieve action with valid company parameter"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()
        request.query_params = {"company": str(self.company.pk)}

        result = permissions.get_company_id("retrieve", request)

        assert result == self.company.pk

    def test_get_company_id_create_with_valid_origin(self, client):
        """Test get_company_id for create action with valid origin step"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()
        request.data = {"origin": {"id": str(self.origin_step.pk)}}

        result = permissions.get_company_id("create", request)

        assert result == self.company.pk

    def test_get_company_id_create_with_invalid_origin(self, client):
        """Test get_company_id for create action with invalid origin step"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()
        request.data = {"origin": {"id": str(uuid.uuid4())}}

        result = permissions.get_company_id("create", request)

        assert result is False

    def test_get_company_id_create_with_missing_origin(self, client):
        """Test get_company_id for create action with missing origin"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()
        request.data = {}

        result = permissions.get_company_id("create", request)

        assert result is False

    def test_get_company_id_update_with_valid_object(self, client):
        """Test get_company_id for update action with valid object"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()

        result = permissions.get_company_id("update", request, self.approval_transition)

        assert result == self.company.pk

    def test_get_company_id_partial_update_with_valid_object(self, client):
        """Test get_company_id for partial_update action with valid object"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()

        result = permissions.get_company_id(
            "partial_update", request, self.approval_transition
        )

        assert result == self.company.pk

    def test_get_company_id_destroy_with_valid_object(self, client):
        """Test get_company_id for destroy action with valid object"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()

        result = permissions.get_company_id(
            "destroy", request, self.approval_transition
        )

        assert result == self.company.pk

    def test_get_company_id_unknown_action(self, client):
        """Test get_company_id for unknown action"""
        permissions = ApprovalTransitionPermissions()
        request = Mock()

        result = permissions.get_company_id("unknown_action", request)

        assert result is False

    def test_approval_transition_list_with_company_param(self, client):
        """Test list endpoint with company parameter"""
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK

    def test_approval_transition_list_without_company_param(self, client):
        """Test list endpoint without company parameter"""
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_approval_transition_retrieve_with_company_param(self, client):
        """Test retrieve endpoint with company parameter"""
        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(self.approval_transition.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK

    def test_approval_transition_retrieve_without_company_param(self, client):
        """Test retrieve endpoint without company parameter"""
        response = client.get(
            path="/{}/{}/".format(self.model, str(self.approval_transition.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
