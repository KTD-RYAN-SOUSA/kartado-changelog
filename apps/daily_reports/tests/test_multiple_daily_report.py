import json
from datetime import datetime
from unittest.mock import PropertyMock, patch

import pytest
from django.db.models.signals import pre_save
from django.http import HttpRequest
from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.companies.models import Firm
from apps.reportings.models import Reporting
from apps.users.models import User
from helpers.testing.fixtures import TestBase, false_permission

from ..models import DailyReportRelation, DailyReportWorker, MultipleDailyReport
from ..serializers import MultipleDailyReportSerializer
from ..signals import auto_add_multiple_daily_report_number

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "MultipleDailyReport"

    ATTRIBUTES = {
        "date": "2021-04-21",
        "dayWithoutWork": False,
        "morningWeather": "SUNNY",
        "afternoonWeather": "SUNNY",
        "nightWeather": "CLOUDY",
        "morningConditions": "FEASIBLE",
        "afternoonConditions": "FEASIBLE",
        "nightConditions": "UNFEASIBLE",
        "morningStart": "08:22:51",
        "morningEnd": "11:22:54",
        "afternoonStart": "13:22:57",
        "afternoonEnd": "17:22:58",
        "nightStart": "20:22:59",
        "nightEnd": "23:23:01",
    }

    def test_multiple_daily_report_list(self, client):
        """
        Ensures we can list using the MultipleDailyReport endpoint
        and the fixture is properly listed
        """

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        # The call was successful
        assert response.status_code == status.HTTP_200_OK

        # The fixture itens are listed
        assert content["meta"]["pagination"]["count"] == 3

    def test_multiple_daily_report_without_company(self, client):
        """
        Ensures calling the MultipleDailyReport endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_multiple_daily_report(self, client):
        """
        Ensures a specific multiple daily report can be fetched using the uuid
        """

        report = MultipleDailyReport.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(report.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_multiple_daily_report(self, client):
        """
        Ensures a new multiple daily report can be created using the endpoint
        """

        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

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
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )

        # Object was created successfully
        content = json.loads(response.content)
        obj_created = MultipleDailyReport.objects.get(pk=content["data"]["id"])
        assert obj_created.legacy_number is None

        assert response.status_code == status.HTTP_201_CREATED

    def test_create_multiple_daily_report_with_blank_legacy_number(self, client):
        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "date": "2021-04-21",
                        "dayWithoutWork": False,
                        "morningWeather": "SUNNY",
                        "afternoonWeather": "SUNNY",
                        "nightWeather": "CLOUDY",
                        "morningConditions": "FEASIBLE",
                        "afternoonConditions": "FEASIBLE",
                        "nightConditions": "UNFEASIBLE",
                        "morningStart": "08:22:51",
                        "morningEnd": "11:22:54",
                        "afternoonStart": "13:22:57",
                        "afternoonEnd": "17:22:58",
                        "nightStart": "20:22:59",
                        "nightEnd": "23:23:01",
                        "legacy_number": "",
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )
        content = json.loads(response.content)
        assert content["data"]["attributes"]["legacyNumber"] == ""
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_multiple_daily_report_with_related_model_field(self, client):
        """
        Ensures a new multiple daily report can be created using the related model fields
        """

        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        self.ATTRIBUTES["createDailyReportWorkers"] = [
            {
                "members": "John, Mark",
                "amount": 3,
                "role": "Manager",
                "firm": {"type": "Firm", "id": firm_id},
            }
        ]

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
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )

        content = json.loads(response.content)

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

        # DailyReportWorker was created and related to new MultipleDailyReport
        worker_relations = content["data"]["relationships"][
            "multipleDailyReportWorkers"
        ]
        assert worker_relations["meta"]["count"] == 1

        # Remove added key
        del self.ATTRIBUTES["createDailyReportWorkers"]

    def test_create_multiple_daily_report_with_worker_relation(self, client):
        """
        Ensures a new multiple daily report can be created while making a relationship
        with another model
        """

        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        # Get DailyReportWorker
        worker = DailyReportWorker.objects.first()
        worker_id = worker.uuid

        worker_relations = [{"type": "DailyReportWorker", "id": str(worker_id)}]

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
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                        "multipleDailyReportWorkers": {"data": worker_relations},
                    },
                }
            },
        )

        content = json.loads(response.content)

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

        # DailyReportWorker was related to new MultipleDailyReport
        worker_relations = content["data"]["relationships"][
            "multipleDailyReportWorkers"
        ]
        assert worker_relations["meta"]["count"] == 1
        assert worker_relations["data"][0]["id"] == str(worker_id)

    def test_create_multiple_daily_report_without_company_id(self, client):
        """
        Ensures a new multiple daily report cannot be created without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_multiple_daily_report_without_permission(self, client):
        """
        Ensures a new multiple daily report cannot be created without
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
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_multiple_daily_report_not_editable(self, client):
        """
        Ensure that a MultipleDailyReport cannot be updated if obj is not editable
        """

        report = MultipleDailyReport.objects.filter(
            company=self.company, editable=False
        ).first()

        # Try to change morning weather
        EATHER_FORECASTS = ("SUNNY", "CLOUDY", "RAINY", "NA")
        default_morning_weather = self.ATTRIBUTES["morningWeather"]

        # Ensures that the new field is differente from the current one
        for i in EATHER_FORECASTS:
            if i == default_morning_weather:
                continue
            morning_weather = i
            break

        self.ATTRIBUTES["morningWeather"] = morning_weather
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(report.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(report.pk),
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        # The object cannot be changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_multiple_daily_report(self, client):
        """
        Ensure a MultipleDailyReport can be updated using the endpoint
        """

        report = MultipleDailyReport.objects.filter(
            company=self.company, editable=True
        ).first()

        # Change morning weather from SUNNY to CLOUDY for the update
        self.ATTRIBUTES["morningWeather"] = "CLOUDY"

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(report.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(report.pk),
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        }
                    },
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_report_with_related_model_field(self, client):
        """
        Ensure related model fields can be used on updates
        """
        report = MultipleDailyReport.objects.filter(company=self.company).first()
        worker = DailyReportWorker.objects.first()

        # First create a relationship we can edit later
        DailyReportRelation.objects.create(
            multiple_daily_report=report, worker=worker, active=True
        )

        # Now we need the worker id
        worker_id = worker.uuid

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        # Add related model edit field
        self.ATTRIBUTES["editDailyReportWorker"] = [
            {
                "id": str(worker_id),
                "firm": {"type": "Firm", "id": str(firm_id)},
                "members": "John, Markus",
                "amount": 40,
                "role": "Leader",
            }
        ]

        # Add relation
        worker_relation = [{"type": "DailyReportWorker", "id": str(worker_id)}]

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(report.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(report.pk),
                    "attributes": self.ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                        "multipleDailyReportWorkers": {"data": worker_relation},
                    },
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

        # Delete added key
        del self.ATTRIBUTES["editDailyReportWorker"]

    def test_delete_daily_report(self, client):
        """
        Ensure a MultipleDailyReport can be deleted using the endpoint
        """

        report = MultipleDailyReport.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(report.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_daily_report_board_item_cascade(self, client):
        """
        Ensures deleting a MultipleDailyReport that has board items leads
        to the board items being deleted alongside.
        """

        firm = Firm.objects.filter(company=self.company).first()

        daily_report = MultipleDailyReport.objects.create(
            date="2023-04-19", company=self.company, firm=firm, number="ABC123"
        )
        daily_report_worker = DailyReportWorker.objects.create(
            company=self.company, amount=3
        )
        daily_report_relation = DailyReportRelation.objects.create(
            multiple_daily_report=daily_report, worker=daily_report_worker
        )

        # Delete the DailyReport
        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(daily_report.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Ensure DailyReport was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not MultipleDailyReport.objects.filter(pk=daily_report.pk).exists()

        # Make sure both the DailyReportWorker and DailyReportRelation were also deleted
        assert not DailyReportWorker.objects.filter(pk=daily_report_worker.pk).exists()
        assert not DailyReportRelation.objects.filter(
            pk=daily_report_relation.pk
        ).exists()

    def test_validate_multiple_daily_report_duration(self, client):
        """
        Ensures work start cannot be later than the work end
        """

        # Backup values for a reset after the test is done
        old_morning_start = self.ATTRIBUTES["morningStart"]
        old_morning_end = self.ATTRIBUTES["morningEnd"]

        # Changes the the morning period so the start is later than the end
        self.ATTRIBUTES["morningStart"] = "12:22:51"
        self.ATTRIBUTES["morningEnd"] = "7:22:51"

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

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
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )

        content = json.loads(response.content)

        # Error creating object
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Descriptive message is given
        expected_message = (
            "kartado.error.base_daily_report.morning_end_should_be_after_morning_start"
        )
        assert content["errors"][0]["detail"] == expected_message

        # Reset changed values
        self.ATTRIBUTES["morningStart"] = old_morning_start
        self.ATTRIBUTES["morningEnd"] = old_morning_end

    def test_create_multiple_daily_report_day_without_work_true(self, client):
        """
        Ensures a MultipleDailyReport can be created without the conditional fields
        when day_without_work is equal to True
        """

        # Only a few attributes are provided
        ATTRIBUTES = {"date": "2021-02-19", "dayWithoutWork": True}

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        # Attempt to create new report
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_report_day_without_work_with_conditional_field(self, client):
        """
        Attempts to create a new MultipleDailyReport with conditional fields
        and day_without_work equals to True
        """

        # Only a few attributes are provided
        ATTRIBUTES = {
            "date": "2021-02-21",
            "dayWithoutWork": True,
            "morningWeather": "SUNNY",
            "nightStart": "20:22:59",
            "nightEnd": "23:23:01",
        }

        # Get same Firm as fixture
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        # Attempt to create new report
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_multiple_daily_with_inspector(self, client):
        ATTRIBUTES = {"date": "2022-07-11"}

        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid
        inspector_id = str(self.user.pk)

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": ATTRIBUTES,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                        "inspector": {"data": {"type": "User", "id": inspector_id}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["inspector"]["id"] == inspector_id

    def test_bulk_delete_multiple_daily_report(self, client):
        """
        Ensure that multiple MultipleDailyReports can be deleted using the endpoint /MultipleDailyReport/Bulk
        """

        report = MultipleDailyReport.objects.filter(
            company=self.company, created_by=self.user, editable=True
        ).first()
        response = client.delete(
            path="/{}/Bulk/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": "MultipleDailyReport",
                    "relationships": {
                        "multiple_daily_reports": {
                            "data": [
                                {
                                    "id": str(report.pk),
                                    "type": "MultipleDailyReport",
                                }
                            ]
                        }
                    },
                }
            },
        )

        # Object was deleted
        assert response.status_code == status.HTTP_200_OK

    def test_handle_m2m_relationships_create_new_relations(self, client):
        """
        Ensures new relationships can be created between a report and workers
        """
        # Create a test report
        firm = Firm.objects.filter(company=self.company).first()
        report = MultipleDailyReport.objects.create(
            date="2023-04-19", company=self.company, firm=firm, number="TEST123"
        )
        # Create test workers
        worker1 = DailyReportWorker.objects.create(
            company=self.company, amount=2, members="Worker 1", firm=firm
        )
        worker2 = DailyReportWorker.objects.create(
            company=self.company, amount=3, members="Worker 2", firm=firm
        )
        # Prepare relationships data
        extracted_relationships = {
            "multiple_daily_report_workers": (DailyReportWorker, [worker1, worker2])
        }
        # Create serializer instance and handle relationships
        serializer = MultipleDailyReportSerializer()
        serializer.handle_m2m_relationships(report, extracted_relationships)
        # Verify relationships were created
        relations = DailyReportRelation.objects.filter(
            multiple_daily_report=report, worker__in=[worker1, worker2]
        )
        histories = DailyReportRelation.history.model.objects.filter(
            multiple_daily_report=report, worker__in=[worker1, worker2]
        )
        assert relations.count() == 2
        assert all(rel.active for rel in relations)
        assert histories.count() == 2

    def test_handle_m2m_relationships_remove_old_relations(self, client):
        """
        Ensures old relationships are removed when not included in new data
        """
        # Create a test report
        firm = Firm.objects.filter(company=self.company).first()
        report = MultipleDailyReport.objects.create(
            date="2023-04-19", company=self.company, firm=firm, number="TEST123"
        )
        # Create workers
        worker1 = DailyReportWorker.objects.create(
            company=self.company, amount=2, members="Worker 1", firm=firm
        )
        worker2 = DailyReportWorker.objects.create(
            company=self.company, amount=3, members="Worker 2", firm=firm
        )
        # Create initial relationships
        DailyReportRelation.objects.create(
            multiple_daily_report=report, worker=worker1, active=True
        )
        DailyReportRelation.objects.create(
            multiple_daily_report=report, worker=worker2, active=True
        )
        # Prepare relationships data with only worker1
        extracted_relationships = {
            "multiple_daily_report_workers": (DailyReportWorker, [worker1])
        }
        # Handle relationships
        serializer = MultipleDailyReportSerializer()
        serializer.handle_m2m_relationships(report, extracted_relationships)

        # Verify only worker1 relationship exists and worker2 was deleted
        assert DailyReportWorker.objects.filter(uuid=worker1.uuid).exists()
        assert not DailyReportWorker.objects.filter(uuid=worker2.uuid).exists()

        histories = DailyReportRelation.history.model.objects.filter(
            multiple_daily_report=report, worker__in=[worker1, worker2]
        )
        assert histories.count() == 3

    def test_handle_m2m_relationships_empty_list(self, client):
        """
        Ensures all relationships are removed when empty list is provided
        """
        # Create a test report
        firm = Firm.objects.filter(company=self.company).first()
        report = MultipleDailyReport.objects.create(
            date="2023-04-19", company=self.company, firm=firm, number="TEST123"
        )
        # Create worker and relationship
        worker = DailyReportWorker.objects.create(
            company=self.company, amount=2, members="Worker 1", firm=firm
        )
        DailyReportRelation.objects.create(
            multiple_daily_report=report, worker=worker, active=True
        )
        # Prepare empty relationships data
        extracted_relationships = {
            "multiple_daily_report_workers": (DailyReportWorker, [])
        }
        # Handle relationships
        serializer = MultipleDailyReportSerializer()
        serializer.handle_m2m_relationships(report, extracted_relationships)
        # Verify worker was deleted
        assert not DailyReportWorker.objects.filter(uuid=worker.uuid).exists()
        histories = DailyReportRelation.history.model.objects.filter(
            multiple_daily_report=report, worker__in=[worker]
        )
        assert histories.count() == 2

    def test_handle_m2m_relationships_none_value(self, client):
        """
        Ensures existing relationships are maintained when None is provided
        """
        # Create a test report
        firm = Firm.objects.filter(company=self.company).first()
        report = MultipleDailyReport.objects.create(
            date="2023-04-19", company=self.company, firm=firm, number="TEST123"
        )
        # Create worker and relationship
        worker = DailyReportWorker.objects.create(
            company=self.company, amount=2, members="Worker 1", firm=firm
        )
        relation = DailyReportRelation.objects.create(
            multiple_daily_report=report, worker=worker, active=True
        )
        # Prepare relationships data with None
        extracted_relationships = {
            "multiple_daily_report_workers": (DailyReportWorker, None)
        }
        # Handle relationships
        serializer = MultipleDailyReportSerializer()
        serializer.handle_m2m_relationships(report, extracted_relationships)
        # Verify relationship still exists
        assert DailyReportWorker.objects.filter(uuid=worker.uuid).exists()
        assert DailyReportRelation.objects.filter(uuid=relation.uuid).exists()

    @patch("apps.daily_reports.serializers.send_daily_report_to_n8n")
    @patch.object(HttpRequest, "body", new_callable=PropertyMock)
    def test_create_multiple_daily_report_sends_to_n8n(
        self, mock_body, mock_send_to_n8n, client
    ):
        """
        Ensures that when a multiple daily report is created, a request is sent to n8n
        with the legacy_number in the payload.
        """
        # Disconnect the signal that auto-adds the number to avoid race conditions
        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        # Get a firm for the report
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        # Set firm_uuids_that_should_call_daily_report_webhook in company metadata
        self.company.metadata["firm_uuids_that_should_call_daily_report_webhook"] = [
            str(firm_id)
        ]
        self.company.save()

        # Define the request data
        request_data = {
            "data": {
                "type": self.model,
                "attributes": self.ATTRIBUTES,
                "relationships": {
                    "company": {
                        "data": {"type": "Company", "id": str(self.company.pk)}
                    },
                    "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                },
            }
        }

        # Set the return value for the mocked body property
        mock_body.return_value = json.dumps(request_data).encode("utf-8")

        # Make the request to create the report
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=request_data,
        )

        # Assert the request was successful
        assert response.status_code == status.HTTP_201_CREATED

        # Get the created instance to check its number
        content = json.loads(response.content)
        instance = MultipleDailyReport.objects.get(pk=content["data"]["id"])

        # Assert that the mock was called
        mock_send_to_n8n.assert_called_once()

        # Get the arguments from the mock call
        call_args, call_kwargs = mock_send_to_n8n.call_args
        raw_body = call_args[0]
        legacy_number = call_args[1]

        # Assert the legacy_number is correct
        assert legacy_number == instance.number

        # Assert the raw_body is correct
        assert raw_body == json.dumps(request_data).encode("utf-8")

    @patch("apps.daily_reports.serializers.send_daily_report_to_n8n")
    @patch.object(HttpRequest, "body", new_callable=PropertyMock)
    def test_create_multiple_daily_report_does_not_send_to_n8n_if_firm_not_in_list(
        self, mock_body, mock_send_to_n8n, client
    ):
        """
        Ensures that when a multiple daily report is created, a request is not sent to n8n
        if the firm uuid is not in the metadata list.
        """
        # Disconnect the signal that auto-adds the number to avoid race conditions
        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        # Get a firm for the report
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        # Set firm_uuids_that_should_call_daily_report_webhook in company metadata to an empty list
        self.company.metadata["firm_uuids_that_should_call_daily_report_webhook"] = []
        self.company.save()

        # Define the request data
        request_data = {
            "data": {
                "type": self.model,
                "attributes": self.ATTRIBUTES,
                "relationships": {
                    "company": {
                        "data": {"type": "Company", "id": str(self.company.pk)}
                    },
                    "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                },
            }
        }

        # Set the return value for the mocked body property
        mock_body.return_value = json.dumps(request_data).encode("utf-8")

        # Make the request to create the report
        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=request_data,
        )

        # Assert the request was successful
        assert response.status_code == status.HTTP_201_CREATED

        # Assert that the mock was not called
        mock_send_to_n8n.assert_not_called()

    def test_get_can_you_edit_when_true(self, client):
        """
        Ensures get_can_you_edit returns True when can_you_edit
        is set to True in context
        """

        report = MultipleDailyReport.objects.filter(company=self.company).first()

        factory = APIRequestFactory()
        django_request = factory.get("/")
        django_request.user = self.user
        request = Request(django_request)

        serializer = MultipleDailyReportSerializer(
            report, context={"request": request, "can_you_edit": True}
        )

        can_you_edit_result = serializer.get_can_you_edit(report)
        assert can_you_edit_result is True

    def test_validate_firm_with_can_create_and_edit_all_firms(self, client):
        """
        Ensures validate_firm returns firm when
        can_create_and_edit_all_firms is True in context
        """

        firm = Firm.objects.first()

        factory = APIRequestFactory()
        django_request = factory.post("/")
        django_request.user = self.user
        request = Request(django_request)

        serializer = MultipleDailyReportSerializer(
            context={"request": request, "can_create_and_edit_all_firms": True}
        )

        validated_firm = serializer.validate_firm(firm)
        assert validated_firm == firm

    def test_get_serializer_context(self, client):
        """
        Ensures get_serializer_context adds can_you_edit and
        can_create_and_edit_all_firms to context when user has permissions
        """

        response = client.get(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_aggregate_resources(self, client):
        """
        Ensures get_aggregate_resources returns aggregated resources
        from reportings and daily report resources
        """

        report = MultipleDailyReport.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/AggregateResources/?company={}".format(
                self.model, str(report.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert "data" in content

    def test_create_multiple_daily_report_with_created_by(self, client):
        """
        Ensures a new multiple daily report can be created with a specified created_by user.
        """
        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        other_user = User.objects.create(username="otheruser", email="other@user.com")

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
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                        "createdBy": {
                            "data": {"type": "User", "id": str(other_user.uuid)}
                        },
                    },
                }
            },
        )

        content = json.loads(response.content)
        assert response.status_code == status.HTTP_201_CREATED
        report = MultipleDailyReport.objects.get(uuid=content["data"]["id"])
        assert report.created_by == other_user

    def test_create_multiple_daily_report_with_inactive_created_by(self, client):
        """
        Ensures a new multiple daily report cannot be created with an inactive created_by user.
        """
        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        other_user = User.objects.create(
            username="otheruser", email="other@user.com", is_active=False
        )

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
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                        "createdBy": {
                            "data": {"type": "User", "id": str(other_user.uuid)}
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_multiple_daily_report_with_nonexistent_created_by(self, client):
        """
        Ensures a new multiple daily report cannot be created with a nonexistent created_by user.
        """
        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

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
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                        "createdBy": {
                            "data": {
                                "type": "User",
                                "id": "00000000-0000-0000-0000-000000000000",
                            }
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.daily_reports.services.send_edited_daily_report_to_n8n")
    def test_update_multiple_daily_report_sends_to_n8n(self, mock_send_to_n8n, client):
        """
        Ensures that when a multiple daily report is updated, a request is sent to n8n
        with the dailyReportUuid in the payload.
        """
        # Get a firm for the report
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        # Set firm_uuids_that_should_call_daily_report_webhook in company metadata
        self.company.metadata["firm_uuids_that_should_call_daily_report_webhook"] = [
            str(firm_id)
        ]
        self.company.save()

        # Create a report first
        create_data = {
            "data": {
                "type": self.model,
                "attributes": self.ATTRIBUTES,
                "relationships": {
                    "company": {
                        "data": {"type": "Company", "id": str(self.company.pk)}
                    },
                    "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                },
            }
        }

        create_response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=create_data,
        )

        assert create_response.status_code == status.HTTP_201_CREATED
        report_data = json.loads(create_response.content)
        report_uuid = report_data["data"]["id"]

        # Define the update request data
        update_data = {
            "data": {
                "type": self.model,
                "id": report_uuid,
                "attributes": {
                    **self.ATTRIBUTES,
                    "notes": "Esta é uma nota atualizada durante a edição.",
                },
                "relationships": {
                    "company": {
                        "data": {"type": "Company", "id": str(self.company.pk)}
                    },
                    "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                },
            }
        }

        # Make the request to update the report
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, report_uuid, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=update_data,
        )

        # Assert the request was successful
        assert response.status_code == status.HTTP_200_OK

        # Assert that the webhook was called with the correct parameters
        mock_send_to_n8n.assert_called_once()
        call_args = mock_send_to_n8n.call_args
        assert call_args[0][1] == report_uuid  # daily_report_uuid parameter
        assert call_args[0][0] is not None  # raw_body parameter

    @patch("apps.daily_reports.services.send_edited_daily_report_to_n8n")
    def test_update_multiple_daily_report_does_not_send_to_n8n_when_firm_not_configured(
        self, mock_send_to_n8n, client
    ):
        """
        Ensures that when a multiple daily report is updated but the firm is not configured
        for webhook, no request is sent to n8n.
        """
        # Get a firm for the report
        firm = DailyReportWorker.objects.first().firm
        firm_id = firm.uuid

        # Do NOT set firm_uuids_that_should_call_daily_report_webhook in company metadata
        # This should prevent the webhook from being called

        # Create a report first
        create_data = {
            "data": {
                "type": self.model,
                "attributes": self.ATTRIBUTES,
                "relationships": {
                    "company": {
                        "data": {"type": "Company", "id": str(self.company.pk)}
                    },
                    "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                },
            }
        }

        create_response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=create_data,
        )

        assert create_response.status_code == status.HTTP_201_CREATED
        report_data = json.loads(create_response.content)
        report_uuid = report_data["data"]["id"]

        # Define the update request data
        update_data = {
            "data": {
                "type": self.model,
                "id": report_uuid,
                "attributes": {
                    **self.ATTRIBUTES,
                    "notes": "Esta é uma nota atualizada durante a edição.",
                },
                "relationships": {
                    "company": {
                        "data": {"type": "Company", "id": str(self.company.pk)}
                    },
                    "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                },
            }
        }

        # Make the request to update the report
        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, report_uuid, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=update_data,
        )

        # Assert the request was successful
        assert response.status_code == status.HTTP_200_OK

        # Assert that the webhook was NOT called
        mock_send_to_n8n.assert_not_called()


class TestUpdateReportingsOnDateChange(TestBase):
    model = "MultipleDailyReport"

    ATTRIBUTES = {
        "dayWithoutWork": False,
        "morningWeather": "SUNNY",
        "afternoonWeather": "SUNNY",
        "nightWeather": "CLOUDY",
        "morningConditions": "FEASIBLE",
        "afternoonConditions": "FEASIBLE",
        "nightConditions": "UNFEASIBLE",
        "morningStart": "08:00:00",
        "morningEnd": "12:00:00",
        "afternoonStart": "13:00:00",
        "afternoonEnd": "17:00:00",
        "nightStart": "20:00:00",
        "nightEnd": "23:00:00",
    }

    @pytest.fixture(autouse=True)
    def _setup_test_data(self, _initial):
        self.firm = DailyReportWorker.objects.first().firm

        # found_at = 2024-01-15
        for i in range(3):
            Reporting.objects.create(
                company=self.company,
                firm=self.firm,
                km=100.0 + i,
                direction="1",
                lane="1",
                found_at=timezone.make_aware(datetime(2024, 1, 15, 10, 0, 0)),
            )

        # found_at = 2024-01-16
        for i in range(2):
            Reporting.objects.create(
                company=self.company,
                firm=self.firm,
                km=200.0 + i,
                direction="1",
                lane="1",
                found_at=timezone.make_aware(datetime(2024, 1, 16, 10, 0, 0)),
            )

        # executed_at = 2024-02-10
        for i in range(2):
            Reporting.objects.create(
                company=self.company,
                firm=self.firm,
                km=300.0 + i,
                direction="1",
                lane="1",
                found_at=timezone.make_aware(datetime(2024, 3, 1, 10, 0, 0)),
                executed_at=timezone.make_aware(datetime(2024, 2, 10, 10, 0, 0)),
            )

        # executed_at = 2024-02-11
        Reporting.objects.create(
            company=self.company,
            firm=self.firm,
            km=400.0,
            direction="1",
            lane="1",
            found_at=timezone.make_aware(datetime(2024, 3, 2, 10, 0, 0)),
            executed_at=timezone.make_aware(datetime(2024, 2, 11, 10, 0, 0)),
        )

    def _create_rdo(self, client, date, firm_id):
        pre_save.disconnect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {**self.ATTRIBUTES, "date": date},
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )

        pre_save.connect(
            auto_add_multiple_daily_report_number, sender=MultipleDailyReport
        )

        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)
        return content["data"]["id"]

    def _update_rdo(self, client, report_uuid, date, firm_id, extra_attrs=None):
        attributes = {**self.ATTRIBUTES, "date": date}
        if extra_attrs:
            attributes.update(extra_attrs)

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, report_uuid, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": report_uuid,
                    "attributes": attributes,
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "firm": {"data": {"type": "Firm", "id": str(firm_id)}},
                    },
                }
            },
        )
        return response

    def test_date_change_with_update_flag_replaces_reportings(self, client):
        """
        Ensures reportings are replaced when date changes
        and update_reportings_on_date_change is True
        """
        report_uuid = self._create_rdo(client, "2024-01-15", str(self.firm.uuid))

        report = MultipleDailyReport.objects.get(pk=report_uuid)
        assert report.reportings.count() == 3

        response = self._update_rdo(
            client,
            report_uuid,
            "2024-01-16",
            str(self.firm.uuid),
            extra_attrs={"update_reportings_on_date_change": True},
        )

        assert response.status_code == status.HTTP_200_OK

        report.refresh_from_db()
        assert report.date.isoformat() == "2024-01-16"
        assert report.reportings.count() == 2

        for r in report.reportings.all():
            assert r.found_at.date().isoformat() == "2024-01-16"

    def test_date_change_without_flag_keeps_reportings(self, client):
        """
        Ensures reportings remain unchanged when date changes
        but update_reportings_on_date_change is not sent
        """
        report_uuid = self._create_rdo(client, "2024-01-15", str(self.firm.uuid))

        report = MultipleDailyReport.objects.get(pk=report_uuid)
        original_reporting_ids = set(report.reportings.values_list("uuid", flat=True))
        assert len(original_reporting_ids) == 3

        response = self._update_rdo(
            client, report_uuid, "2024-01-16", str(self.firm.uuid)
        )

        assert response.status_code == status.HTTP_200_OK

        report.refresh_from_db()
        assert report.date.isoformat() == "2024-01-16"
        current_reporting_ids = set(report.reportings.values_list("uuid", flat=True))
        assert current_reporting_ids == original_reporting_ids

    def test_date_change_with_flag_false_keeps_reportings(self, client):
        """
        Ensures reportings remain unchanged when date changes
        and update_reportings_on_date_change is explicitly False
        """
        report_uuid = self._create_rdo(client, "2024-01-15", str(self.firm.uuid))

        report = MultipleDailyReport.objects.get(pk=report_uuid)
        original_reporting_ids = set(report.reportings.values_list("uuid", flat=True))

        response = self._update_rdo(
            client,
            report_uuid,
            "2024-01-16",
            str(self.firm.uuid),
            extra_attrs={"update_reportings_on_date_change": False},
        )

        assert response.status_code == status.HTTP_200_OK

        report.refresh_from_db()
        current_reporting_ids = set(report.reportings.values_list("uuid", flat=True))
        assert current_reporting_ids == original_reporting_ids

    def test_date_change_to_date_with_no_reportings_clears_all(self, client):
        """
        Ensures all reportings are cleared when date changes
        to a date with no matching reportings
        """
        report_uuid = self._create_rdo(client, "2024-01-15", str(self.firm.uuid))

        report = MultipleDailyReport.objects.get(pk=report_uuid)
        assert report.reportings.count() == 3

        response = self._update_rdo(
            client,
            report_uuid,
            "2024-01-17",
            str(self.firm.uuid),
            extra_attrs={"update_reportings_on_date_change": True},
        )

        assert response.status_code == status.HTTP_200_OK

        report.refresh_from_db()
        assert report.reportings.count() == 0

    def test_same_date_with_flag_does_not_change_reportings(self, client):
        """
        Ensures reportings are not touched when the date does not change,
        even if update_reportings_on_date_change is True
        """
        report_uuid = self._create_rdo(client, "2024-01-15", str(self.firm.uuid))

        report = MultipleDailyReport.objects.get(pk=report_uuid)
        original_reporting_ids = set(report.reportings.values_list("uuid", flat=True))
        assert len(original_reporting_ids) == 3

        response = self._update_rdo(
            client,
            report_uuid,
            "2024-01-15",
            str(self.firm.uuid),
            extra_attrs={"update_reportings_on_date_change": True},
        )

        assert response.status_code == status.HTTP_200_OK

        report.refresh_from_db()
        current_reporting_ids = set(report.reportings.values_list("uuid", flat=True))
        assert current_reporting_ids == original_reporting_ids

    def test_date_change_uses_company_metadata_config(self, client):
        """
        Ensures the executed_at field is used for linking reportings when
        field_to_automatically_link_reportings_to_rdo is set in company metadata
        """
        self.company.metadata[
            "field_to_automatically_link_reportings_to_rdo"
        ] = "executed_at"
        self.company.save()

        report_uuid = self._create_rdo(client, "2024-02-10", str(self.firm.uuid))

        report = MultipleDailyReport.objects.get(pk=report_uuid)
        assert report.reportings.count() == 2

        response = self._update_rdo(
            client,
            report_uuid,
            "2024-02-11",
            str(self.firm.uuid),
            extra_attrs={"update_reportings_on_date_change": True},
        )

        assert response.status_code == status.HTTP_200_OK

        report.refresh_from_db()
        assert report.reportings.count() == 1

        linked_reporting = report.reportings.first()
        assert linked_reporting.executed_at.date().isoformat() == "2024-02-11"

    def test_date_change_defaults_to_found_at_when_no_config(self, client):
        """
        Ensures found_at is used as default when
        field_to_automatically_link_reportings_to_rdo is not set
        """
        self.company.metadata.pop("field_to_automatically_link_reportings_to_rdo", None)
        self.company.save()

        report_uuid = self._create_rdo(client, "2024-01-15", str(self.firm.uuid))

        report = MultipleDailyReport.objects.get(pk=report_uuid)
        assert report.reportings.count() == 3

        response = self._update_rdo(
            client,
            report_uuid,
            "2024-01-16",
            str(self.firm.uuid),
            extra_attrs={"update_reportings_on_date_change": True},
        )

        assert response.status_code == status.HTTP_200_OK

        report.refresh_from_db()
        assert report.reportings.count() == 2

        for r in report.reportings.all():
            assert r.found_at.date().isoformat() == "2024-01-16"

    def test_date_change_with_flag_records_history(self, client):
        """
        Ensures a new history entry is recorded when reportings
        are updated due to date change
        """
        report_uuid = self._create_rdo(client, "2024-01-15", str(self.firm.uuid))

        report = MultipleDailyReport.objects.get(pk=report_uuid)
        history_count_before = report.history.count()

        response = self._update_rdo(
            client,
            report_uuid,
            "2024-01-16",
            str(self.firm.uuid),
            extra_attrs={"update_reportings_on_date_change": True},
        )

        assert response.status_code == status.HTTP_200_OK

        report.refresh_from_db()
        assert report.history.count() > history_count_before

        latest_history = report.history.first()
        assert latest_history.date.isoformat() == "2024-01-16"
