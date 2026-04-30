import pytest
from rest_framework import status

from apps.approval_flows.models import ApprovalFlow, ApprovalStep, ApprovalTransition
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestApprovalStepView(TestBase):
    model = "ApprovalStep"

    @pytest.fixture(autouse=True)
    def setup_approval_step_data(self, _initial):
        # Create an approval flow for testing
        self.approval_flow = ApprovalFlow.objects.create(
            name="Test Approval Flow", target_model="TestModel", company=self.company
        )
        # Create approval steps for testing
        self.approval_step = ApprovalStep.objects.create(
            name="Test Step", approval_flow=self.approval_flow
        )
        self.approval_step2 = ApprovalStep.objects.create(
            name="Test Step 2", approval_flow=self.approval_flow
        )

    def test_get_queryset_list_with_company_param(self, client):
        """Test get_queryset for list action with company parameter"""
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK
        # Verify that the queryset contains our test data

        assert (
            response.data["meta"]["pagination"]["count"] >= 2
        )  # Should include our test steps

    def test_get_queryset_list_without_company_param(self, client):
        """Test get_queryset for list action without company parameter returns empty"""
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_queryset_retrieve_with_company_param(self, client):
        """Test get_queryset for retrieve action with company parameter"""
        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(self.approval_step.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK
        # Verify the correct step is returned
        assert response.data["uuid"] == str(self.approval_step.pk)

    def test_get_queryset_list_with_self_permission_non_clustered(self, client):
        false_permission(
            self.user, self.company, self.model, allowed="self", all_true=False
        )

        if self.company.metadata is None:
            self.company.metadata = {}

        if "is_clustered_access_request" in self.company.metadata:
            self.company.metadata.pop("is_clustered_access_request")
        self.company.save()

        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] >= 2

    def test_get_queryset_list_with_self_permission_clustered(self, client):
        false_permission(self.user, self.company, self.model, allowed="self")

        if self.company.metadata is None:
            self.company.metadata = {}

        self.company.metadata["is_clustered_access_request"] = True
        self.company.save()

        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] >= 0

    def test_get_queryset_list_with_all_permission_clustered(self, client):
        false_permission(
            self.user, self.company, self.model, allowed="all", all_true=True
        )

        if self.company.metadata is None:
            self.company.metadata = {}

        self.company.metadata["is_clustered_access_request"] = True
        self.company.save()

        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] >= 0

    def test_get_queryset_list_with_all_permission_non_clustered(self, client):
        false_permission(
            self.user, self.company, self.model, allowed="all", all_true=True
        )

        if self.company.metadata is None:
            self.company.metadata = {}

        if "is_clustered_access_request" in self.company.metadata:
            self.company.metadata.pop("is_clustered_access_request")
        self.company.save()

        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] >= 2

    def test_get_queryset_list_with_none_permission(self, client):
        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] == 0


class TestApprovalTransitionView(TestBase):
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
        # Create approval transitions for testing
        self.approval_transition = ApprovalTransition.objects.create(
            name="Test Transition",
            origin=self.origin_step,
            destination=self.destination_step,
        )
        self.approval_transition2 = ApprovalTransition.objects.create(
            name="Test Transition 2",
            origin=self.destination_step,
            destination=self.origin_step,
        )

    def test_get_queryset_list_with_company_param(self, client):
        """Test get_queryset for list action with company parameter"""
        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK
        # Verify that the queryset contains our test data

        assert (
            response.data["meta"]["pagination"]["count"] >= 2
        )  # Should include our test steps

    def test_get_queryset_list_without_company_param(self, client):
        """Test get_queryset for list action without company parameter returns empty"""
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_queryset_retrieve_with_company_param(self, client):
        """Test get_queryset for retrieve action with company parameter"""
        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(self.approval_transition.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK
        # Verify the correct transition is returned
        assert response.data["uuid"] == str(self.approval_transition.pk)
