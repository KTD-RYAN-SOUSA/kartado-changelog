import pytest

from apps.approval_flows.models import ApprovalFlow, ApprovalStep
from apps.approval_flows.serializers import ApprovalStepSerializer
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestApprovalStepSerializer(TestBase):
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
        # Create serializer instance
        self.serializer = ApprovalStepSerializer()

    def test_get_target_model(self, client):
        """Test get_target_model method returns the correct target model from approval flow"""
        result = self.serializer.get_target_model(self.approval_step)

        assert result == "TestModel"
        assert result == self.approval_flow.target_model

    def test_get_company(self, client):
        """Test get_company method returns the correct company from approval flow"""
        result = self.serializer.get_company(self.approval_step)

        assert result == self.company
        assert result == self.approval_flow.company
