import json

import pytest
from rest_framework import status

from helpers.testing.fixtures import TestBase, false_permission

from ..models import (
    DailyReport,
    DailyReportEquipment,
    DailyReportExternalTeam,
    DailyReportRelation,
    DailyReportSignaling,
    DailyReportVehicle,
    DailyReportWorker,
)

pytestmark = pytest.mark.django_db


class TestDailyReport(TestBase):
    model = "DailyReportRelation"

    ATTRIBUTES = {"active": True}

    def test_daily_report_relation_list(self, client):
        """
        Ensures we can list using the DailyReportRelation endpoint
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

        # The fixture itens are listed + items with relations manually setted by the fixtures (e.g. multiple_daily_reports in workers)
        assert content["meta"]["pagination"]["count"] == 12

    def test_daily_report_relation_without_company(self, client):
        """
        Ensures calling the DailyReportRelation endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_daily_report_relation(self, client):
        """
        Ensures a specific daily report relation can be fetched using the uuid
        """

        relation = DailyReportRelation.objects.first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(relation.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_daily_report_relation_with_worker(self, client):
        """
        Ensures a new relation can be created between DailyReport
        and DailyReportWorker
        """

        # Get relation objects (from fixtures)
        report = DailyReport.objects.first()
        report_id = report.uuid
        worker = DailyReportWorker.objects.first()
        worker_id = worker.uuid

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
                        "dailyReport": {
                            "data": {
                                "type": "DailyReport",
                                "id": str(report_id),
                            }
                        },
                        "worker": {
                            "data": {
                                "type": "DailyReportWorker",
                                "id": str(worker_id),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_relation_with_external_team(self, client):
        """
        Ensures a new relation can be created between DailyReport
        and DailyReportExternalTeam
        """

        # Get relation objects (from fixtures)
        report = DailyReport.objects.first()
        report_id = report.uuid
        team = DailyReportExternalTeam.objects.first()
        team_id = team.uuid

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
                        "dailyReport": {
                            "data": {
                                "type": "DailyReport",
                                "id": str(report_id),
                            }
                        },
                        "externalTeam": {
                            "data": {
                                "type": "DailyReportExternalTeam",
                                "id": str(team_id),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_relation_with_equipment(self, client):
        """
        Ensures a new relation can be created between DailyReport
        and DailyReportEquipment
        """

        # Get relation objects (from fixtures)
        report = DailyReport.objects.first()
        report_id = report.uuid
        equipment = DailyReportEquipment.objects.first()
        equipment_id = equipment.uuid

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
                        "dailyReport": {
                            "data": {
                                "type": "DailyReport",
                                "id": str(report_id),
                            }
                        },
                        "equipment": {
                            "data": {
                                "type": "DailyReportEquipment",
                                "id": str(equipment_id),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_relation_with_vehicle(self, client):
        """
        Ensures a new relation can be created between DailyReport
        and DailyReportVehicle
        """

        # Get relation objects (from fixtures)
        report = DailyReport.objects.first()
        report_id = report.uuid
        vehicle = DailyReportVehicle.objects.first()
        vehicle_id = vehicle.uuid

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
                        "dailyReport": {
                            "data": {
                                "type": "DailyReport",
                                "id": str(report_id),
                            }
                        },
                        "vehicle": {
                            "data": {
                                "type": "DailyReportVehicle",
                                "id": str(vehicle_id),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_relation_with_signaling(self, client):
        """
        Ensures a new relation can be created between DailyReport
        and DailyReportSignaling
        """

        # Get relation objects (from fixtures)
        report = DailyReport.objects.first()
        report_id = report.uuid
        signaling = DailyReportSignaling.objects.first()
        signaling_id = signaling.uuid

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
                        "dailyReport": {
                            "data": {
                                "type": "DailyReport",
                                "id": str(report_id),
                            }
                        },
                        "signaling": {
                            "data": {
                                "type": "DailyReportSignaling",
                                "id": str(signaling_id),
                            }
                        },
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_daily_report_relation_without_company_id(self, client):
        """
        Ensures a new daily report relation cannot be created
        without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_daily_report_relation_without_permission(self, client):
        """
        Ensures a new daily report worker cannot be created without
        the proper permissions
        """

        # Get relation objects (from fixtures)
        report = DailyReportWorker.objects.first()
        report_id = report.uuid
        worker = DailyReportWorker.objects.first()
        worker_id = worker.uuid

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
                        },
                        "dailyReport": {
                            "data": {
                                "type": "DailyReport",
                                "id": str(report_id),
                            }
                        },
                        "worker": {
                            "data": {
                                "type": "DailyReportWorker",
                                "id": str(worker_id),
                            }
                        },
                    },
                }
            },
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_daily_report_relation(self, client):
        """
        Ensure a DailyReportRelation can be updated using the endpoint
        """

        relation = DailyReportRelation.objects.first()

        # Change from True to False for the update
        self.ATTRIBUTES["active"] = False

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(relation.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(relation.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_daily_report_worker(self, client):
        """
        Ensure a DailyReportRelation can be deleted using the endpoint
        """

        relation = DailyReportRelation.objects.first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(relation.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT
