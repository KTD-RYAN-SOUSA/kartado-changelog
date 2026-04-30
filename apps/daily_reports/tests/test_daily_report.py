import json

import pytest
from django.db.models.signals import pre_save
from rest_framework import status

from helpers.testing.fixtures import TestBase, false_permission

from ..models import DailyReport, DailyReportRelation, DailyReportWorker
from ..signals import auto_add_daily_report_number

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "DailyReport"

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

    def test_daily_report_list(self, client):
        """
        Ensures we can list using the DailyReport endpoint
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
        assert content["meta"]["pagination"]["count"] == 2

    def test_daily_report_without_company(self, client):
        """
        Ensures calling the DailyReport endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_daily_report(self, client):
        """
        Ensures a specific daily report can be fetched using the uuid
        """

        report = DailyReport.objects.filter(company=self.company).first()

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

    def test_create_daily_report(self, client):
        """
        Ensures a new daily report can be created using the endpoint
        """

        pre_save.disconnect(auto_add_daily_report_number, sender=DailyReport)

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
                        "dailyReportWorkers": {"data": []},
                        "dailyReportExternalTeams": {"data": []},
                        "dailyReportEquipment": {"data": []},
                        "dailyReportVehicles": {"data": []},
                        "dailyReportSignaling": {"data": []},
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_with_related_model_field(self, client):
        """
        Ensures a new daily report can be created using the related model fields
        """

        pre_save.disconnect(auto_add_daily_report_number, sender=DailyReport)

        self.ATTRIBUTES["createDailyReportWorkers"] = [
            {
                "firm": {
                    "type": "Firm",
                    "id": "eb093034-7f05-4d93-8a7d-cdf8ee04923d",
                },
                "members": "John, Mark",
                "amount": 3,
                "role": "Manager",
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
                        "dailyReportWorkers": {"data": []},
                        "dailyReportExternalTeams": {"data": []},
                        "dailyReportEquipment": {"data": []},
                        "dailyReportVehicles": {"data": []},
                        "dailyReportSignaling": {"data": []},
                    },
                }
            },
        )

        content = json.loads(response.content)

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

        # DailyReportWorker was created and related to new DailyReport
        worker_relations = content["data"]["relationships"]["dailyReportWorkers"]
        assert worker_relations["meta"]["count"] == 1

        # Remove added key
        del self.ATTRIBUTES["createDailyReportWorkers"]

    def test_create_daily_report_with_worker_relation(self, client):
        """
        Ensures a new daily report can be created while making a relationship
        with another model
        """

        pre_save.disconnect(auto_add_daily_report_number, sender=DailyReport)

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
                        "dailyReportWorkers": {"data": worker_relations},
                        "dailyReportExternalTeams": {"data": []},
                        "dailyReportEquipment": {"data": []},
                        "dailyReportVehicles": {"data": []},
                        "dailyReportSignaling": {"data": []},
                    },
                }
            },
        )

        content = json.loads(response.content)

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

        # DailyReportWorker was related to new DailyReport
        worker_relations = content["data"]["relationships"]["dailyReportWorkers"]
        assert worker_relations["meta"]["count"] == 1
        assert worker_relations["data"][0]["id"] == str(worker_id)

    def test_create_report_without_related_model_relationships(self, client):
        """
        Ensures a new daily report can be created without making a relationship
        with another sibling model
        """

        pre_save.disconnect(auto_add_daily_report_number, sender=DailyReport)

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

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_without_company_id(self, client):
        """
        Ensures a new daily report cannot be created without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_daily_report_without_permission(self, client):
        """
        Ensures a new daily report cannot be created without
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

    def test_update_daily_report(self, client):
        """
        Ensure a DailyReport can be updated using the endpoint
        """

        report = DailyReport.objects.filter(company=self.company).first()

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
                        },
                        "dailyReportWorkers": {"data": []},
                        "dailyReportExternalTeams": {"data": []},
                        "dailyReportEquipment": {"data": []},
                        "dailyReportVehicles": {"data": []},
                        "dailyReportSignaling": {"data": []},
                    },
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_report_with_related_model_field(self, client):
        report = DailyReport.objects.filter(company=self.company).first()
        worker = DailyReportWorker.objects.first()

        # First create a relationship we can edit later
        DailyReportRelation.objects.create(
            daily_report=report, worker=worker, active=True
        )

        # Now we need the worker id
        worker_id = worker.uuid

        # Add related model edit field
        self.ATTRIBUTES["editDailyReportWorker"] = [
            {
                "id": str(worker_id),
                "firm": {
                    "type": "Firm",
                    "id": "eb093034-7f05-4d93-8a7d-cdf8ee04923d",
                },
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
                        "dailyReportWorkers": {"data": worker_relation},
                        "dailyReportExternalTeams": {"data": []},
                        "dailyReportEquipment": {"data": []},
                        "dailyReportVehicles": {"data": []},
                        "dailyReportSignaling": {"data": []},
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
        Ensure a DailyReport can be deleted using the endpoint
        """

        report = DailyReport.objects.filter(company=self.company).first()

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
        Ensures deleting a DailyReport that has board items leads
        to the board items being deleted alongside.
        """

        daily_report = DailyReport.objects.create(
            date="2023-04-19", company=self.company, number="ABC123"
        )
        daily_report_worker = DailyReportWorker.objects.create(
            company=self.company, amount=3
        )
        daily_report_relation = DailyReportRelation.objects.create(
            daily_report=daily_report, worker=daily_report_worker
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
        assert not DailyReport.objects.filter(pk=daily_report.pk).exists()

        # Make sure both the DailyReportWorker and DailyReportRelation were also deleted
        assert not DailyReportWorker.objects.filter(pk=daily_report_worker.pk).exists()
        assert not DailyReportRelation.objects.filter(
            pk=daily_report_relation.pk
        ).exists()

    def test_validate_daily_report_duration(self, client):
        """
        Ensures work start cannot be later than the work end
        """

        # Backup values for a reset after the test is done
        old_morning_start = self.ATTRIBUTES["morningStart"]
        old_morning_end = self.ATTRIBUTES["morningEnd"]

        # Changes the the morning period so the start is later than the end
        self.ATTRIBUTES["morningStart"] = "12:22:51"
        self.ATTRIBUTES["morningEnd"] = "7:22:51"

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

    def test_validate_daily_report_date(self, client):
        """
        Ensures two different reports cannot have the same date for
        the same company
        """

        # Get existing report
        existing_report = DailyReport.objects.filter(company=self.company).first()

        # Backup old date value for a reset after the test
        old_date_value = self.ATTRIBUTES["date"]

        # Set the date of the new report to be the same as the existing one
        self.ATTRIBUTES["date"] = existing_report.date.strftime("%Y-%m-%d")

        # Attempt to create new report
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

        content = json.loads(response.content)

        # Error creating object
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Descriptive message is given
        expected_message = "Os campos date, company devem criar um set único."
        assert content["errors"][0]["detail"] == expected_message

        # Reset changed value
        self.ATTRIBUTES["date"] = old_date_value

    def test_create_daily_report_day_without_work_true(self, client):
        """
        Ensures a DailyReport can be created without the conditional fields
        when day_without_work is equal to True
        """

        # Only a few attributes are provided
        ATTRIBUTES = {"date": "2021-02-19", "dayWithoutWork": True}

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
                        "dailyReportWorkers": {"data": []},
                        "dailyReportExternalTeams": {"data": []},
                        "dailyReportEquipment": {"data": []},
                        "dailyReportVehicles": {"data": []},
                        "dailyReportSignaling": {"data": []},
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_report_day_without_work_with_conditional_field(self, client):
        """
        Attempts to create a new DailyReport with conditional fields
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
                        "dailyReportWorkers": {"data": []},
                        "dailyReportExternalTeams": {"data": []},
                        "dailyReportEquipment": {"data": []},
                        "dailyReportVehicles": {"data": []},
                        "dailyReportSignaling": {"data": []},
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_with_inspector(self, client):
        ATTRIBUTES = {"date": "2022-07-11"}

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
                        "inspector": {"data": {"type": "User", "id": inspector_id}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["inspector"]["id"] == inspector_id
