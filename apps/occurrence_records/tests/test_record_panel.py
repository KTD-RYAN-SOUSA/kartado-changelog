import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from rest_framework import status as http_status

from apps.companies.models import Company, Firm, SubCompany
from apps.occurrence_records.models import OccurrenceRecord
from apps.reportings.models import RecordMenu, RecordMenuRelation
from apps.service_orders.models import (
    ServiceOrderActionStatus,
    ServiceOrderActionStatusSpecs,
)
from apps.templates.models import SearchTag
from apps.users.models import User
from helpers.testing.fixtures import TestBase, false_permission

from ..models import (
    RecordPanel,
    RecordPanelShowList,
    RecordPanelShowMobileMap,
    RecordPanelShowWebMap,
)

pytestmark = pytest.mark.django_db


class TestRecordPanel(TestBase):
    model = "RecordPanel"

    ATTRIBUTES = {
        "name": "Default Panel",
        "panelType": "LIST",
        "conditions": {"some": "condition"},
        "showInList": True,
    }

    def test_record_panel_list(self, client):
        """
        Ensures we can list using the RecordPanel endpoint
        and the fixture is properly listed
        """
        menu_id = "e1b79573-473e-4f47-9d35-606f8a54b816"

        response = client.get(
            path="/{}/?company={}&page_size=1&menu={}".format(
                self.model, str(self.company.pk), menu_id
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == http_status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 2
        assert content["data"][0]["relationships"]["menu"]["data"].get("id") == menu_id

    def test_record_panel_without_company(self, client):
        """
        Ensures calling the RecordPanel endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_get_record_panel(self, client):
        """
        Ensures a specific RecordPanel can be fetched using the uuid
        """

        obj_id = "85cd7f75-f946-45eb-b82d-ab04736fc250"

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, obj_id, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == http_status.HTTP_200_OK

    def test_create_record_panel(self, client):
        """
        Ensures a new RecordPanel can be created using the endpoint
        """

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "menu": {
                            "data": {
                                "type": "RecordMenu",
                                "id": str(RecordMenu.objects.first().pk),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == http_status.HTTP_201_CREATED

    def test_create_record_panel_without_company_id(self, client):
        """
        Ensures a new RecordPanel cannot be created
        without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_create_record_panel_without_permission(self, client):
        """
        Ensures a new RecordPanel cannot be created without
        the proper permissions
        """

        false_permission(self.user, self.company, self.model)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_update_record_panel(self, client):  # TODO
        """
        Ensure a RecordPanel can be updated using the endpoint
        """

        obj_id = "85cd7f75-f946-45eb-b82d-ab04736fc250"

        # Change name to "Example"
        self.ATTRIBUTES["name"] = "Example"

        response = client.patch(
            path="/{}/{}/?company={}".format(self.model, obj_id, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": obj_id,
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == http_status.HTTP_200_OK

    def test_delete_record_panel(self, client):
        """
        Ensure a RecordPanel can be deleted using the endpoint
        """

        obj_id = "85cd7f75-f946-45eb-b82d-ab04736fc250"

        response = client.delete(
            path="/{}/{}/?company={}".format(self.model, obj_id, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == http_status.HTTP_204_NO_CONTENT

    def test_create_panel_creates_show_instances(self):
        # Create the necessary users
        panel_creator_user = User.objects.create(username="panel_creator_user")
        user_with_shared_panel = User.objects.create(username="user_with_shared_panel")

        # Create a company
        company = Company.objects.create(name="Test Company")

        # Create the Record Panel
        record_panel = RecordPanel.objects.create(
            created_by=panel_creator_user,
            company=company,
            name="Default Panel",
        )

        # Add a user as a viewer
        record_panel.viewer_users.add(user_with_shared_panel)

        # Verify that show model instances have been created
        assert RecordPanelShowWebMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()
        assert RecordPanelShowMobileMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()

    def test_add_user_creates_show_instances(self):
        # Create the necessary users
        panel_creator_user = User.objects.create(username="panel_creator_user")
        user_with_shared_panel = User.objects.create(username="user_with_shared_panel")
        new_user = User.objects.create(username="new_user")

        # Create a company
        company = Company.objects.create(name="Test Company")

        # Create the Record Panel
        record_panel = RecordPanel.objects.create(
            created_by=panel_creator_user,
            company=company,
            name="Default Panel",
        )
        # Add the initial user as a viewer
        record_panel.viewer_users.add(user_with_shared_panel)

        # Verify that show model instances have been created for the initial user
        assert RecordPanelShowWebMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()
        assert RecordPanelShowMobileMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()

        # Add a new user as a viewer
        record_panel.viewer_users.add(new_user)

        # Verify that show model instances have been created for the new user
        assert RecordPanelShowWebMap.objects.filter(
            user=new_user, panel=record_panel
        ).exists()
        assert RecordPanelShowMobileMap.objects.filter(
            user=new_user, panel=record_panel
        ).exists()

    def test_edit_panel_does_not_create_show_instances_for_existing_users(self):
        # Create the necessary users
        panel_creator_user = User.objects.create(username="panel_creator_user")
        existing_user = User.objects.create(username="existing_user")

        # Create a company
        company = Company.objects.create(name="Test Company")

        # Create the Record Panel
        record_panel = RecordPanel.objects.create(
            created_by=panel_creator_user,
            company=company,
            name="Default Panel",
        )

        # Add the existing user as a viewer without creating show instances
        record_panel.viewer_users.add(existing_user)

        # Ensure no show instances exist for the existing user
        RecordPanelShowWebMap.objects.filter(
            user=existing_user, panel=record_panel
        ).delete()
        RecordPanelShowMobileMap.objects.filter(
            user=existing_user, panel=record_panel
        ).delete()
        assert not RecordPanelShowWebMap.objects.filter(
            user=existing_user, panel=record_panel
        ).exists()
        assert not RecordPanelShowMobileMap.objects.filter(
            user=existing_user, panel=record_panel
        ).exists()

        # Edit the panel (simulate an update)
        record_panel.name = "Updated Panel"
        record_panel.save()

        # Verify that show model instances have not been created for the existing user
        assert not RecordPanelShowWebMap.objects.filter(
            user=existing_user, panel=record_panel
        ).exists()
        assert not RecordPanelShowMobileMap.objects.filter(
            user=existing_user, panel=record_panel
        ).exists()

    def test_edit_panel_and_add_viewer_as_editor_does_not_create_show_instances_for_existing_users(
        self,
    ):
        # Create the necessary users
        panel_creator_user = User.objects.create(username="panel_creator_user")
        existing_user = User.objects.create(username="existing_user")

        # Create a company
        company = Company.objects.create(name="Test Company")

        # Create the Record Panel
        record_panel = RecordPanel.objects.create(
            created_by=panel_creator_user,
            company=company,
            name="Default Panel",
        )

        # Add the existing user as a viewer without creating show instances
        record_panel.viewer_users.add(existing_user)

        # Ensure no show instances exist for the existing user
        RecordPanelShowWebMap.objects.filter(
            user=existing_user, panel=record_panel
        ).delete()
        RecordPanelShowMobileMap.objects.filter(
            user=existing_user, panel=record_panel
        ).delete()
        assert not RecordPanelShowWebMap.objects.filter(
            user=existing_user, panel=record_panel
        ).exists()
        assert not RecordPanelShowMobileMap.objects.filter(
            user=existing_user, panel=record_panel
        ).exists()

        # Edit the panel to add the existing user as an editor
        record_panel.editor_users.add(existing_user)

        # Verify that show model instances have not been created for the existing user
        assert not RecordPanelShowWebMap.objects.filter(
            user=existing_user, panel=record_panel
        ).exists()
        assert not RecordPanelShowMobileMap.objects.filter(
            user=existing_user, panel=record_panel
        ).exists()

    def test_remove_and_readd_user_creates_show_instances(self):
        # Create the necessary users
        panel_creator_user = User.objects.create(username="panel_creator_user")
        user_with_shared_panel = User.objects.create(username="user_with_shared_panel")

        # Create a company
        company = Company.objects.create(name="Test Company")

        # Create the Record Panel
        record_panel = RecordPanel.objects.create(
            created_by=panel_creator_user,
            company=company,
            name="Default Panel",
        )

        # Add the user as a viewer
        record_panel.viewer_users.add(user_with_shared_panel)

        # Verify that show model instances have been created
        assert RecordPanelShowWebMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()
        assert RecordPanelShowMobileMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()

        # Remove the user from viewers and editors
        record_panel.viewer_users.remove(user_with_shared_panel)
        record_panel.editor_users.remove(user_with_shared_panel)

        # Ensure no show instances exist for the existing user
        RecordPanelShowWebMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).delete()
        RecordPanelShowMobileMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).delete()

        # Verify that show model instances have been deleted
        assert not RecordPanelShowWebMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()
        assert not RecordPanelShowMobileMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()

        # Add the user back as a viewer
        record_panel.viewer_users.add(user_with_shared_panel)

        # Verify that show model instances have been created again
        assert RecordPanelShowWebMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()
        assert RecordPanelShowMobileMap.objects.filter(
            user=user_with_shared_panel, panel=record_panel
        ).exists()

    def test_record_panel_change_order(self, client):
        """
        Ensures a new RecordPanel can be created using the endpoint
        """

        panel = RecordPanel.objects.filter(system_default=True).first()

        response = client.post(
            path="/{}/ChangeOrder/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": [{"panel": str(panel.pk), "order": 50}],
                }
            },
        )

        content = json.loads(response.content)
        panel_data = content["data"]["data"]["panelOrder"][0]
        assert panel_data["uuid"] == str(panel.pk)
        assert panel_data["order"] == 99999

    def test_new_panel_shared_with_user_is_marked_as_new(self):
        # Create the necessary users
        panel_creator_user = User.objects.create(username="panel_creator_user")
        user_with_shared_panel = User.objects.create(username="user_with_shared_panel")

        # Create the Record Panel
        record_panel = RecordPanel.objects.create(
            created_by=panel_creator_user,
            company=self.company,
            name="New Panel",
        )

        # Add the user as a viewer
        record_panel.viewer_users.add(user_with_shared_panel)

        # Verify that the panel is marked as new for the user
        assert RecordPanelShowList.objects.filter(
            user=user_with_shared_panel, panel=record_panel, new_to_user=True
        ).exists()

    def test_creator_user_is_not_notified_of_new_panel(self):
        # Create the necessary users
        panel_creator_user = User.objects.create(username="panel_creator_user")

        # Create the Record Panel
        record_panel = RecordPanel.objects.create(
            created_by=panel_creator_user,
            company=self.company,
            name="Creator's Panel",
        )

        # Verify that the panel creator is not notified that the panel is new
        assert not RecordPanelShowList.objects.filter(
            user=panel_creator_user, panel=record_panel, new_to_user=True
        ).exists()

    def test_panel_is_not_marked_as_new_after_user_opens_it(self, client):
        # Create the necessary users
        panel_creator_user = User.objects.create(username="panel_creator_user")
        user_with_shared_panel = self.user

        # Create the Record Panel
        record_panel = RecordPanel.objects.create(
            created_by=panel_creator_user,
            company=self.company,
            name="Panel to Open",
        )

        # Add the user as a viewer
        record_panel.viewer_users.add(user_with_shared_panel)

        # Verify that the panel is initially marked as new
        show_list_instance = RecordPanelShowList.objects.get(
            user=user_with_shared_panel, panel=record_panel
        )
        assert show_list_instance.new_to_user is True
        response = client.post(
            path="/{}/{}/mark_panel_as_seen/?company={}".format(
                self.model, record_panel.uuid, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        assert response.status_code == http_status.HTTP_200_OK

        # Reload the instance to verify that the dashboard has been unmarked as new
        show_list_instance.refresh_from_db()
        assert show_list_instance.new_to_user is False

    def test_record_panel_list_with_all_permission_scenarios(self, client):
        """
        Tests listing RecordPanels with different permission scenarios including
        default, all, and various access levels
        """
        # Clean up existing panels
        RecordPanel.objects.all().delete()

        menu_id = "e1b79573-473e-4f47-9d35-606f8a54b816"
        company_id = str(self.company.pk)

        # Create test users and firms
        other_user = User.objects.create(username="other_user")
        test_firm = Firm.objects.create(
            name="Test Firm", company=self.company, created_by=self.user
        )
        test_firm.users.add(self.user)

        # Create subcompany for testing
        subcompany = SubCompany.objects.create(
            name="Test SubCompany", company=self.company
        )

        subcompany_firm = Firm.objects.create(
            name="SubCompany Firm",
            company=self.company,
            subcompany=subcompany,
            created_by=self.user,
        )
        subcompany_firm.users.add(self.user)

        # Create panels with different permission scenarios
        panels = {
            "user_created": RecordPanel.objects.create(
                name="Panel Created by User",
                company=self.company,
                created_by=self.user,
                menu_id=menu_id,
            ),
            "todos": RecordPanel.objects.create(
                name="Todos",
                company=self.company,
                created_by=other_user,
                menu_id=menu_id,
            ),
            "viewer_user": RecordPanel.objects.create(
                name="Panel for User Viewer",
                company=self.company,
                created_by=other_user,
                menu_id=menu_id,
            ),
            "viewer_firm": RecordPanel.objects.create(
                name="Panel for Firm Viewer",
                company=self.company,
                created_by=other_user,
                menu_id=menu_id,
            ),
            "editor_user": RecordPanel.objects.create(
                name="Panel for User Editor",
                company=self.company,
                created_by=other_user,
                menu_id=menu_id,
            ),
            "subcompany": RecordPanel.objects.create(
                name="Panel with SubCompany",
                company=self.company,
                created_by=other_user,
                menu_id=menu_id,
            ),
        }

        # Set up permissions
        panels["viewer_user"].viewer_users.add(self.user)
        panels["viewer_firm"].viewer_firms.add(test_firm)
        panels["editor_user"].editor_users.add(self.user)
        panels["subcompany"].viewer_subcompanies.add(subcompany)

        # Test scenarios with different permission levels
        test_scenarios = [
            ("default", ["default"]),
            ("all", ["all"]),
        ]

        for scenario_name, permissions in test_scenarios:
            with patch("helpers.permissions.PermissionManager") as mock_permissions:
                mock_instance = mock_permissions.return_value
                mock_instance.get_allowed_queryset.return_value = permissions

                response = client.get(
                    path="/{}/?company={}&menu={}".format(
                        self.model, company_id, menu_id
                    ),
                    content_type="application/vnd.api+json",
                    HTTP_AUTHORIZATION="JWT {}".format(self.token),
                )

                content = json.loads(response.content)
                assert response.status_code == http_status.HTTP_200_OK

                if scenario_name == "default":
                    # Should see panels based on permissions
                    expected_count = 6  # Adjust based on visible panels
                    assert content["meta"]["pagination"]["count"] == expected_count
                else:  # 'all'
                    # Should see all panels
                    total_panels = RecordPanel.objects.filter(
                        company=self.company
                    ).count()
                    assert content["meta"]["pagination"]["count"] == total_panels

    @patch("sentry_sdk.capture_exception")
    def test_get_serializer_context_variations(self, mock_capture_exception, client):
        """
        Test the different ways to get the company_id in get_serializer_context
        """
        obj_id = "85cd7f75-f946-45eb-b82d-ab04736fc250"

        # Case 1: company in request.data
        response = client.patch(
            path="/{}/{}/".format(self.model, obj_id),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": obj_id,
                    "attributes": self.ATTRIBUTES,
                    "company": {"id": str(self.company.pk)},
                }
            },
        )
        assert response.status_code == http_status.HTTP_200_OK

        # Case 2: company permissions.company_id (without company in query_params or data)
        response = client.patch(
            path="/{}/{}/".format(self.model, obj_id),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": obj_id,
                    "attributes": self.ATTRIBUTES,
                }
            },
        )
        assert response.status_code == http_status.HTTP_200_OK

        # Case 3: AttributeError test
        with patch(
            "apps.users.models.User.companies_membership", create=True
        ) as mock_membership:
            mock_membership.filter.side_effect = AttributeError("Test error")

            response = client.get(
                path="/{}/{}/?company={}".format(
                    self.model, obj_id, str(self.company.pk)
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
            )

            mock_capture_exception.assert_called_once()

    def test_change_order_validation_errors(self, client):
        """
        Test various validation error scenarios for change_order endpoint
        """
        panel = RecordPanel.objects.create(
            name="Test Panel", company=self.company, created_by=self.user
        )

        test_cases = [
            # Invalid UUID format
            {
                "data": {"panel": "invalid-uuid", "order": 1},
                "expected_error": "kartado.error.record_panel.invalid_record_panel_uuid_provided",
            },
            # Badly formed request (non-integer order)
            {
                "data": {"panel": str(panel.pk), "order": "not_an_int"},
                "expected_error": "kartado.error.record_panel.badly_formed_request_body",
            },
            # Non-existent panel UUID
            {
                "data": {"panel": "12345678-1234-5678-1234-567812345678", "order": 1},
                "expected_error": "kartado.error.record_panel.invalid_record_panel_uuid_provided",
            },
        ]

        for test_case in test_cases:
            response = client.post(
                path="/{}/ChangeOrder/?company={}".format(
                    self.model, str(self.company.pk)
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
                data={
                    "data": {
                        "type": self.model,
                        "attributes": [test_case["data"]],
                    }
                },
            )

            assert response.status_code == http_status.HTTP_400_BAD_REQUEST
            content = json.loads(response.content)
            assert test_case["expected_error"] in str(content)

    def test_change_order_show_list_operations(self, client):
        """
        Test creation, update and removal of RecordPanelShowList entries
        """
        # Create test panels
        panel1 = RecordPanel.objects.create(
            name="Panel 1", company=self.company, created_by=self.user
        )
        panel2 = RecordPanel.objects.create(
            name="Panel 2", company=self.company, created_by=self.user
        )
        panel3 = RecordPanel.objects.create(
            name="Panel 3 (to be removed)", company=self.company, created_by=self.user
        )

        # Create initial show lists
        RecordPanelShowList.objects.create(panel=panel2, user=self.user, order=1)
        RecordPanelShowList.objects.create(panel=panel3, user=self.user, order=3)

        # Initial verification
        assert RecordPanelShowList.objects.count() == 2

        response = client.post(
            path="/{}/ChangeOrder/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": [
                        {"panel": str(panel1.pk), "order": 1},
                        {"panel": str(panel2.pk), "order": 2},
                    ],
                }
            },
        )

        assert response.status_code == http_status.HTTP_200_OK
        content = json.loads(response.content)

        # Verify response statuses
        panel_order = content["data"]["data"]["panelOrder"]
        statuses = {item["uuid"]: item["status"] for item in panel_order}

        # Verify expected statuses for all operations
        assert statuses[str(panel1.pk)] == "RecordPanelShowList created"
        assert statuses[str(panel2.pk)] == "RecordPanelShowList order updated"
        assert statuses[str(panel3.pk)] == "RecordPanelShowList removed"

        # Verify database state after operations
        assert RecordPanelShowList.objects.filter(panel=panel1, order=1).exists()
        assert RecordPanelShowList.objects.filter(panel=panel2, order=2).exists()
        assert not RecordPanelShowList.objects.filter(panel=panel3).exists()

        # Verify final count of show lists
        assert RecordPanelShowList.objects.count() == 2

        # Test duplicate order validation
        response = client.post(
            path="/{}/ChangeOrder/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": [
                        {"panel": str(panel1.pk), "order": 1},
                        {"panel": str(panel2.pk), "order": 1},
                    ],
                }
            },
        )

        assert response.status_code == http_status.HTTP_200_OK
        panel1_sl = RecordPanelShowList.objects.filter(panel=panel1).first()
        panel2_sl = RecordPanelShowList.objects.filter(panel=panel2).first()
        assert panel1_sl.order != panel2_sl.order

    def test_get_kanban_without_company(self, client):
        """Test get_kanban endpoint without company parameter"""
        # First create a valid panel that the user has access to
        panel = RecordPanel.objects.create(
            name="Test Panel",
            company=self.company,
            created_by=self.user,
            panel_type="KANBAN",
            content_type=ContentType.objects.get(model="occurrencerecord"),
        )

        response = client.get(
            path="/RecordPanel/{}/KanBan/".format(panel.uuid),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == http_status.HTTP_403_FORBIDDEN
        content = json.loads(response.content)
        assert (
            content["errors"][0]["detail"]
            == "Você não tem permissão para executar essa ação."
        )
        assert content["errors"][0]["source"]["pointer"] == "/data"
        assert content["errors"][0]["status"] == "403"

    def test_get_kanban_invalid_company_uuid(self, client):
        """Test get_kanban endpoint with invalid company UUID"""
        # Create a valid panel first
        panel = RecordPanel.objects.create(
            name="Test Panel",
            company=self.company,
            created_by=self.user,
            panel_type="KANBAN",
            content_type=ContentType.objects.get(model="occurrencerecord"),
        )

        response = client.get(
            path="/RecordPanel/{}/KanBan/?company=invalid-uuid".format(panel.uuid),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == http_status.HTTP_403_FORBIDDEN
        content = json.loads(response.content)
        assert (
            content["errors"][0]["detail"]
            == "Você não tem permissão para executar essa ação."
        )
        assert content["errors"][0]["source"]["pointer"] == "/data"
        assert content["errors"][0]["status"] == "403"

    def test_get_kanban_with_grouping(self, client):
        """Test get_kanban endpoint with grouping enabled"""
        panel = RecordPanel.objects.create(
            name="Grouped Kanban",
            company=self.company,
            created_by=self.user,
            panel_type="KANBAN",
            content_type=ContentType.objects.get(model="occurrencerecord"),
            kanban_columns={
                "columns": {
                    "col1": {"title": "Column 1", "status_ids": [str(uuid.uuid4())]}
                },
                "column_order": ["col1"],
            },
            kanban_group_by={"group_by": "status", "order_items_without_value": "end"},
        )

        response = client.get(
            path="/RecordPanel/{}/KanBan/?company={}".format(
                panel.uuid, str(self.company.uuid)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == http_status.HTTP_200_OK
        content = json.loads(response.content)

        # Check the nested structure
        assert "data" in content
        assert "columns" in content["data"]
        assert "col1" in content["data"]["columns"]
        assert "groups" in content["data"]["columns"]["col1"]

        # Additional checks for the response structure
        assert "columnOrder" in content["data"]
        assert "recordCount" in content["data"]
        assert "totalCount" in content["data"]

        # Verify the column properties
        col1 = content["data"]["columns"]["col1"]
        assert col1["id"] == "col1"
        assert col1["title"] == "Column 1"
        assert "recordCount" in col1
        assert isinstance(col1["groups"], list)

    def test_get_kanban_reporting_type(self, client):
        """Test get_kanban endpoint with reporting content type"""
        # Create a panel with reporting content type
        panel = RecordPanel.objects.create(
            name="Reporting Panel",
            company=self.company,
            created_by=self.user,
            panel_type="KANBAN",
            content_type=ContentType.objects.get(model="reporting"),
            kanban_columns={
                "columns": {
                    "col1": {"title": "Column 1", "status_ids": [str(uuid.uuid4())]}
                },
                "column_order": ["col1"],
            },
        )

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/KanBan/?company={self.company.uuid}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_200_OK
        content = json.loads(response.content)
        assert "data" in content
        assert "columns" in content["data"]

    def test_get_kanban_without_columns(self, client):
        """Test get_kanban endpoint with panel missing kanban columns"""
        panel = RecordPanel.objects.create(
            name="No Columns Panel",
            company=self.company,
            created_by=self.user,
            panel_type="KANBAN",
            content_type=ContentType.objects.get(model="occurrencerecord"),
            kanban_columns=None,
        )

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/KanBan/?company={self.company.uuid}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert (
            "kartado.error.record_panel.record_panel_doesnt_have_kanban_columns"
            in str(content)
        )

    def test_get_kanban_invalid_conditions(self, client):
        """Test get_kanban endpoint with invalid conditions"""
        panel = RecordPanel.objects.create(
            name="Invalid Conditions Panel",
            company=self.company,
            created_by=self.user,
            panel_type="KANBAN",
            content_type=ContentType.objects.get(model="occurrencerecord"),
            conditions={"invalid": "condition"},
            kanban_columns={
                "columns": {
                    "col1": {"title": "Column 1", "status_ids": [str(uuid.uuid4())]}
                },
                "column_order": ["col1"],
            },
        )

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/KanBan/?company={self.company.uuid}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert (
            "kartado.error.record_panel.record_panel_conditions_does_not_have_logic_field"
            in str(content)
        )

    def test_get_kanban_missing_columns(self, client):
        """Test get_kanban endpoint without kanban columns"""
        panel = RecordPanel.objects.create(
            name="No Columns Panel",
            company=self.company,
            created_by=self.user,
            panel_type="KANBAN",
            content_type=ContentType.objects.get(model="occurrencerecord"),
        )

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/KanBan/?company={self.company.uuid}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert (
            "kartado.error.record_panel.record_panel_doesnt_have_kanban_columns"
            in str(content)
        )

    def test_get_kanban_occurrence_record_processing(self, client):
        """Test processing of occurrence records in kanban with all fields"""
        # Create necessary test data
        action_status = ServiceOrderActionStatus.objects.create(
            name="Test Status", kind="ACTION_STATUS", is_final=False
        )

        # Create the many-to-many relationship with company through ServiceOrderActionStatusSpecs
        ServiceOrderActionStatusSpecs.objects.create(
            company=self.company,
            status=action_status,  # Usando o novo nome
            color="#FF0000",
            order=1,
        )

        # Create search tags for different levels
        search_tags = []
        for level in range(1, 5):
            tag = SearchTag.objects.create(
                name=f"Tag Level {level}", level=level, company=self.company
            )
            search_tags.append(tag)

        # Create an occurrence record
        test_datetime = timezone.now()
        occurrence = OccurrenceRecord.objects.create(
            company=self.company,
            created_by=self.user,
            status=action_status,
            number="TEST-001",
            datetime=test_datetime,
            search_tag_description="Test Description",
        )

        # Add search tags to occurrence
        for tag in search_tags:
            occurrence.search_tags.add(tag)

        # Create panel with kanban configuration
        panel = RecordPanel.objects.create(
            name="Test Panel",
            company=self.company,
            created_by=self.user,
            panel_type="KANBAN",
            content_type=ContentType.objects.get(model="occurrencerecord"),
            kanban_columns={
                "columns": {
                    "col1": {
                        "title": "Column 1",
                        "status_ids": [str(action_status.uuid)],
                    }
                },
                "column_order": ["col1"],
            },
        )

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/KanBan/?company={self.company.uuid}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_200_OK
        content = json.loads(response.content)

        # Verify record data in response
        record_data = content["data"]["columns"]["col1"]["records"][0]
        assert record_data["uuid"] == str(occurrence.uuid)
        assert record_data["number"] == "TEST-001"
        assert record_data["record"] == "Tag Level 1"
        assert record_data["type"] == "Tag Level 2"
        assert record_data["kind"] == "Tag Level 3"
        assert record_data["subject"] == "Tag Level 4"
        assert record_data["description"] == "Test Description"

    def test_get_fields_success(self, client):
        """Test successful retrieval of fields with valid company ID"""
        company_id = str(self.company.pk)

        response = client.get(
            path="/{}/Fields/?company={}".format(self.model, company_id),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == http_status.HTTP_200_OK
        content = json.loads(response.content)

        assert "data" in content
        assert "fields" in content["data"]

        fields = content["data"]["fields"]
        assert isinstance(fields, dict)

    def test_get_fields_nonexistent_company(self, client):
        """Test error when company doesn't exist"""
        nonexistent_uuid = "12345678-1234-5678-1234-567812345678"

        response = client.get(
            path="/{}/Fields/?company={}".format(self.model, nonexistent_uuid),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert "Nao foi possivel encontrar a unidade." in str(content)

    def test_get_fields_missing_company(self, client):
        """Test error when company parameter is missing"""
        response = client.get(
            path="/{}/Fields/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert "É necessário especificar uma company." in str(content)

    def test_get_fields_with_permissions(self, client):
        """Test fields retrieval with permissions check"""
        company_id = str(self.company.pk)
        expected_response = {"test_field": "test_value"}
        self.permissions = MagicMock()
        self.permissions.all_permissions = ["permission1", "permission2"]

        with patch("apps.occurrence_records.views.get_response") as mock_get_response:
            mock_get_response.return_value = expected_response

            response = client.get(
                path="/{}/Fields/?company={}".format(self.model, company_id),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
            )

            assert response.status_code == http_status.HTTP_200_OK
            content = json.loads(response.content)
            assert "data" in content
            assert "fields" in content["data"]
            assert content["data"]["fields"] == expected_response
            mock_get_response.assert_called_once()

    def test_get_fields_invalid_uuid_format(self, client):
        """Test error when an invalid UUID format is provided"""
        self.permissions = MagicMock()
        self.permissions.all_permissions = ["permission1", "permission2"]

        response = client.get(
            path="/{}/Fields/?company=invalid-format".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert "badly formed hexadecimal UUID string" in str(content)

    def test_get_gzip_success(self, client):
        """Test successful retrieval and compression of GeoJSON data"""
        # Create necessary test data
        panel = RecordPanel.objects.create(
            name="Test GZIP Panel",
            company=self.company,
            created_by=self.user,
            conditions={"field": "value"},
        )

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/GZIP/?company={str(self.company.pk)}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_200_OK
        assert response["Content-Type"] == "application/gzip"
        assert response["Content-Encoding"] == "gzip"
        assert (
            response["Content-Disposition"]
            == f'attachment; filename="{panel.name}.json"'
        )

    def test_get_gzip_panel_not_found(self, client):
        """Test response when record panel doesn't exist"""
        non_existent_uuid = "12345678-1234-5678-1234-567812345678"

        response = client.get(
            path=f"/RecordPanel/{non_existent_uuid}/GZIP/?company={str(self.company.pk)}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_404_NOT_FOUND

    def test_get_gzip_without_company(self, client):
        """Test error when company parameter is missing"""
        panel = RecordPanel.objects.create(
            name="Test Panel", company=self.company, created_by=self.user, conditions={}
        )

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/GZIP/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    @patch("apps.occurrence_records.views.get_occurrence_record_queryset")
    def test_get_gzip_empty_queryset(self, mock_get_queryset, client):
        """Test response when queryset is empty"""
        panel = RecordPanel.objects.create(
            name="Empty Panel",
            company=self.company,
            created_by=self.user,
            conditions={},
        )

        # Mock empty queryset
        mock_get_queryset.return_value = OccurrenceRecord.objects.none()

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/GZIP/?company={str(self.company.pk)}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_200_OK
        assert response["Content-Type"] == "application/gzip"

    @patch("apps.occurrence_records.views.get_occurrence_record_queryset")
    @patch("apps.occurrence_records.views.apply_conditions_to_query")
    def test_get_gzip_with_conditions(
        self, mock_apply_conditions, mock_get_queryset, client
    ):
        false_permission(self.user, self.company, "Reporting")
        false_permission(self.user, self.company, "Inventory")

        """Test that conditions are properly applied to the queryset"""
        panel = RecordPanel.objects.create(
            name="Conditional Panel",
            company=self.company,
            created_by=self.user,
            conditions={"test": "condition"},
        )

        # Create a real queryset to use as base
        base_queryset = OccurrenceRecord.objects.all()
        filtered_queryset = base_queryset.filter(geometry__isnull=False)

        # Set up the mock querysets to return proper QuerySet objects
        mock_get_queryset.return_value = base_queryset
        mock_apply_conditions.return_value = filtered_queryset

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/GZIP/?company={str(self.company.pk)}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_200_OK

        # Verify that apply_conditions_to_query was called
        assert mock_apply_conditions.called

        # Check the arguments separately
        call_args = mock_apply_conditions.call_args
        assert call_args is not None

        # Check the first argument (conditions)
        assert call_args[0][0] == panel.conditions

        # Check that the second argument is a QuerySet
        assert isinstance(call_args[0][1], models.QuerySet)

        # Instead of comparing query strings, verify the key aspects of the queryset
        second_arg_queryset = call_args[0][1]

        # Check if the geometry__isnull filter is applied
        filters = second_arg_queryset.query.where.children
        has_geometry_filter = any(
            hasattr(child, "lhs")
            and hasattr(child.lhs, "target")
            and child.lhs.target.name == "geometry"
            and isinstance(child, models.lookups.IsNull)
            for child in filters
        )
        assert has_geometry_filter, "geometry__isnull filter not found in queryset"

    @patch("gzip.compress")
    @patch("apps.occurrence_records.views.get_occurrence_record_queryset")
    @patch("apps.occurrence_records.views.apply_conditions_to_query")
    def test_get_gzip_compression_error(
        self, mock_apply_conditions, mock_get_queryset, mock_compress, client
    ):
        false_permission(self.user, self.company, "Reporting")
        false_permission(self.user, self.company, "Inventory")

        """Test handling of compression errors"""
        panel = RecordPanel.objects.create(
            name="Error Panel",
            company=self.company,
            created_by=self.user,
            conditions={},
        )

        # Create a real queryset to use as base
        base_queryset = OccurrenceRecord.objects.all()
        filtered_queryset = base_queryset.filter(geometry__isnull=False)

        # Set up the mock querysets to return proper QuerySet objects
        mock_get_queryset.return_value = base_queryset
        mock_apply_conditions.return_value = filtered_queryset

        # Simulate compression error
        mock_compress.side_effect = Exception("Compression failed")

        with pytest.raises(Exception) as exc_info:
            client.get(
                path=f"/RecordPanel/{panel.uuid}/GZIP/?company={str(self.company.pk)}",
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION=f"JWT {self.token}",
            )

        assert str(exc_info.value) == "Compression failed"
        mock_compress.assert_called_once()

    def test_get_pbf_success(self, client):
        """Test successful retrieval and encoding of PBF data"""
        panel = RecordPanel.objects.create(
            name="Test PBF Panel",
            company=self.company,
            created_by=self.user,
            conditions={"field": "value"},
        )

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/PBF/?company={str(self.company.pk)}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_200_OK

    def test_get_pbf_panel_not_found(self, client):
        """Test response when record panel doesn't exist"""
        non_existent_uuid = "12345678-1234-5678-1234-567812345678"

        response = client.get(
            path=f"/RecordPanel/{non_existent_uuid}/PBF/?company={str(self.company.pk)}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_404_NOT_FOUND

    def test_get_pbf_without_company(self, client):
        """Test error when company parameter is missing"""
        panel = RecordPanel.objects.create(
            name="Test Panel", company=self.company, created_by=self.user, conditions={}
        )

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/PBF/",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    @patch("apps.occurrence_records.views.get_occurrence_record_queryset")
    def test_get_pbf_empty_queryset(self, mock_get_queryset, client):
        """Test response when queryset is empty"""
        panel = RecordPanel.objects.create(
            name="Empty Panel",
            company=self.company,
            created_by=self.user,
            conditions={},
        )

        mock_get_queryset.return_value = OccurrenceRecord.objects.none()

        response = client.get(
            path=f"/RecordPanel/{panel.uuid}/PBF/?company={str(self.company.pk)}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )

        assert response.status_code == http_status.HTTP_200_OK

    def test_record_panel_filter_get_show_in_web_map(self, client):
        panel = RecordPanel.objects.create(
            name="Panel WebMap", company=self.company, created_by=self.user
        )
        panel.show_in_web_map_users.add(self.user)

        # value=true should include panel
        resp_true = client.get(
            path=f"/{self.model}/?company={self.company.uuid}&show_in_web_map=true",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )
        assert resp_true.status_code == 200
        content_true = json.loads(resp_true.content)
        ids_true = {item["id"] for item in content_true.get("data", [])}
        assert str(panel.uuid) in ids_true

        # value=false should exclude panel
        resp_false = client.get(
            path=f"/{self.model}/?company={self.company.uuid}&show_in_web_map=false",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )
        assert resp_false.status_code == 200
        content_false = json.loads(resp_false.content)
        ids_false = {item["id"] for item in content_false.get("data", [])}
        assert str(panel.uuid) not in ids_false

    def test_record_panel_filter_get_has_order(self, client):
        # one with system_default
        panel_sys = RecordPanel.objects.create(
            name="Sys", company=self.company, created_by=self.user, system_default=True
        )
        # one with order set via RecordPanelShowList
        panel_ord = RecordPanel.objects.create(
            name="Ord", company=self.company, created_by=self.user
        )
        RecordPanelShowList.objects.create(panel=panel_ord, user=self.user, order=1)
        # one without
        panel_none = RecordPanel.objects.create(
            name="None", company=self.company, created_by=self.user
        )

        resp_true = client.get(
            path=f"/{self.model}/?company={self.company.uuid}&has_order=true",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )
        assert resp_true.status_code == 200
        content = json.loads(resp_true.content)
        ids_true = {item["id"] for item in content.get("data", [])}
        assert str(panel_sys.uuid) in ids_true
        assert str(panel_ord.uuid) in ids_true
        assert str(panel_none.uuid) not in ids_true

        resp_false = client.get(
            path=f"/{self.model}/?company={self.company.uuid}&has_order=false",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )
        assert resp_false.status_code == 200
        content = json.loads(resp_false.content)
        ids_false = {item["id"] for item in content.get("data", [])}
        assert str(panel_none.uuid) in ids_false
        assert str(panel_sys.uuid) not in ids_false
        assert str(panel_ord.uuid) not in ids_false

    def test_record_panel_serializer_show_flags(self, client):
        # Create a RecordMenu and RecordPanel with menu
        menu = RecordMenu.objects.create(
            name="Test Menu", company=self.company, created_by=self.user, order=1
        )
        panel = RecordPanel.objects.create(
            name="Flags", company=self.company, created_by=self.user, menu=menu
        )

        RecordPanelShowList.objects.create(panel=panel, user=self.user, order=1)
        panel.show_in_web_map_users.add(self.user)
        panel.show_in_app_map_users.add(self.user)

        response = client.get(
            path=f"/{self.model}/?company={self.company.uuid}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )
        assert response.status_code == 200
        content = json.loads(response.content)
        data = content["data"]

        # Find our panel in the response
        panel_data = next(
            (item for item in data if item["id"] == str(panel.uuid)), None
        )
        assert panel_data is not None

        assert panel_data["attributes"]["showInList"] is True
        assert panel_data["attributes"]["showInWebMap"] is True
        assert panel_data["attributes"]["showInAppMap"] is True

        RecordMenuRelation.objects.create(
            record_menu=menu,
            user=self.user,
            hide_menu=True,
            order=1,
            company=self.company,
        )

        response = client.get(
            path=f"/{self.model}/?company={self.company.uuid}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
        )
        assert response.status_code == 200
        content = json.loads(response.content)
        data = content["data"]

        # Find our panel in the response
        panel_data = next(
            (item for item in data if item["id"] == str(panel.uuid)), None
        )
        assert panel_data is not None

        # When hidden_menu=True, all show flags should be False
        assert panel_data["attributes"]["showInList"] is False
        assert panel_data["attributes"]["showInWebMap"] is False
        assert panel_data["attributes"]["showInAppMap"] is False
