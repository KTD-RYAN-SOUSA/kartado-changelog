from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import serializers

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import UserPermission
from apps.to_dos.models import ToDoAction, ToDoActionStep
from helpers.apps.access_request import create_access_request
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestAccessRequestHelper(TestBase):
    model = "Helpers"

    def get_validated_data(self):
        validated_data = {
            "user": self.user,
            "company": self.company,
            "expiration_date": date.today() + timedelta(days=365),
            "description": "Descrição Teste",
            "approved": False,
            "done": False,
            "permissions": UserPermission.objects.first(),
            "created_by": self.user,
        }

        return validated_data

    @pytest.mark.django_db
    def test_create_access_request_successful(self):
        """Test create the access request with auto_execute_transition"""
        validated_data = self.get_validated_data()

        instance = create_access_request(validated_data, self.company.uuid)

        assert instance is not None
        assert instance.company_id == self.company.uuid
        assert instance.user == self.user
        assert instance.done is True

    @pytest.mark.django_db
    def test_func_with_nonexistent_id(self):
        """Test create the access request with a noexistend company id"""
        try:
            validated_data = self.get_validated_data()

            create_access_request(validated_data, "nonexistent_id")

        except serializers.ValidationError as e:
            assert (
                str(e.detail[0])
                == "Não foi possível criar a requisição de acesso. Contate nossa equipe."
            )
        else:
            pytest.fail("The ValidationError exception was not raised")

    @pytest.mark.django_db
    @patch("helpers.apps.access_request.generate_todo")
    @patch("helpers.apps.access_request.ToDoActionStep.objects.filter")
    @patch("helpers.apps.access_request.ToDoAction.objects.filter")
    def test_create_access_request_with_mocked_to_dos(
        self,
        mock_to_do_action_filter,
        mock_to_do_action_step_filter,
        mock_generate_todo,
    ):
        """Test create the access request with to do notifications"""

        # Create or get mocks
        approval_step = ApprovalStep.objects.get(
            pk="3ed67d5d-68fa-4ecb-9b37-49f45e88cda4"
        )
        mocked_to_do_action = ToDoAction.objects.create(
            company_group=self.company.company_group,
            created_by=self.user,
            name="To Do Action Teste",
            default_options="see",
        )
        mocked_to_do_action_step = ToDoActionStep.objects.create(
            todo_action=mocked_to_do_action,
            approval_step=approval_step,
            destinatary="responsible",
        )

        # Config mock returns
        mock_to_do_action_step_queryset = MagicMock()
        mock_to_do_action_step_queryset.__len__.return_value = 1
        mock_to_do_action_step_queryset.first.return_value = mocked_to_do_action_step
        mock_to_do_action_step_filter.return_value = mock_to_do_action_step_queryset

        mock_to_do_action_filter.return_value.first.return_value = mocked_to_do_action
        mock_generate_todo.return_value = None

        # Test the function
        validated_data = self.get_validated_data()

        instance = create_access_request(validated_data, self.company.uuid)

        assert instance is not None
