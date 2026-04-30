import json
from datetime import datetime

import pytest
from django.db.models import Q
from rest_framework import status

from apps.companies.models import Firm
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import RecordMenu, Reporting, ReportingInReporting
from apps.service_orders.models import ServiceOrderActionStatus
from apps.templates.models import MobileSync
from apps.users.models import User
from apps.work_plans.asynchronous import (
    process_job_async_batch,
    process_job_rep_in_rep_batches,
)
from apps.work_plans.models import Job
from helpers.strings import get_obj_from_path
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestJob(TestBase):
    model = "Job"

    def test_list_jobs(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        # Test without direction for kms

        self.company.metadata["use_direction"] = False
        self.company.save()

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_jobs_without_queryset(self, client):
        false_permission(self.user, self.company, self.model, allowed="none")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        false_permission(self.user, self.company, self.model, allowed="self")

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_jobs_without_company(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_jobs_without_uuid(self, client):
        response = client.get(
            path="/{}/?company={}".format(self.model, "test"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_job(self, client):
        job = Job.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(job.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        # Test without direction for kms

        self.company.metadata["use_direction"] = False
        self.company.save()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(job.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_job(self, client):
        reporting_base = Reporting.objects.filter(company=self.company)[0]

        reporting = Reporting.objects.create(
            company=self.company,
            occurrence_type=reporting_base.occurrence_type,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test",
        )

        occ_type = OccurrenceType.objects.filter(
            company=self.company,
            occurrence_kind="1",
            form_fields__fields__isnull=False,
        )[0]

        inventory = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="2"
        ).exclude(pk=reporting.pk)[0]

        menu = RecordMenu.objects.first()

        fields = [a["apiName"] for a in occ_type.form_fields["fields"]]

        inventory.form_data[fields[0]] = 50.0
        inventory.save()

        user = User.objects.first()
        firm = Firm.objects.get(uuid="4ee50e2c-be0b-4d32-9341-efb4c0d89818")

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "metadata": {},
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "reportings": {
                            "data": [{"type": "Reporting", "id": str(reporting.pk)}]
                        },
                        "inventory": {
                            "data": [{"type": "Inventory", "id": str(inventory.pk)}]
                        },
                        "occurrence_type": {
                            "data": [
                                {
                                    "type": "OccurrenceType",
                                    "id": str(occ_type.pk),
                                }
                            ]
                        },
                        "menu": {"data": {"type": "RecordMenu", "id": str(menu.pk)}},
                        "worker": {"data": {"type": "User", "id": str(user.pk)}},
                        "firm": {"data": {"type": "Firm", "id": str(firm.pk)}},
                        "watcher_users": {
                            "data": [
                                {
                                    "type": "User",
                                    "id": str(user.pk),
                                }
                            ]
                        },
                        "watcher_firms": {
                            "data": [
                                {
                                    "type": "Firm",
                                    "id": str(firm.pk),
                                }
                            ]
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)
        new_job_id = content["data"]["id"]

        # Call scheduled task manually
        process_job_async_batch()

        # We'll need a new GET because the async data will not be yet included in the POST response
        # NOTE: The `while` is meant to simulate the long polling
        processing_async_creation = True
        while processing_async_creation:
            response = client.get(
                path="/{}/{}/?company={}".format(
                    self.model, new_job_id, str(self.company.pk)
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
                data={},
            )
            attributes = json.loads(response.content)["data"]["attributes"]
            processing_async_creation = attributes["processingAsyncCreation"]

        # Calculated fields are working properly
        assert attributes["reportingCount"] == 2
        assert attributes["executedReportings"] == 1
        assert attributes["progress"] == 0.5

    def test_create_job_with_reporting_without_job(self, client):
        reporting = Reporting.objects.filter(company=self.company, job__isnull=False)[0]

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "metadata": {},
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "reportings": {
                            "data": [{"type": "Reporting", "id": str(reporting.pk)}]
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_job_with_reporting_from_inspection(self, client):
        inventory = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="2"
        ).first()

        occ_type = OccurrenceType.objects.filter(occurrence_kind="1")

        inspection = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="1"
        ).first()

        menu = RecordMenu.objects.first()

        therapy_data = {
            "therapy": [
                {
                    "occurrence_type": str(occ_type[0].pk),
                    "description": "teste 1",
                    "km": 2,
                    "end_km": 10,
                },
                {
                    "occurrence_type": str(occ_type[1].pk),
                    "description": "teste 2",
                    "km": 20,
                    "end_km": 30,
                },
            ]
        }

        inspection.form_data.update(therapy_data)
        inspection.save()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "metadata": {},
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "inventory": {
                            "data": [{"type": "Inventory", "id": str(inventory.pk)}]
                        },
                        "inspection": {
                            "data": {
                                "type": "Reporting",
                                "id": str(inspection.pk),
                            }
                        },
                        "menu": {"data": {"type": "RecordMenu", "id": str(menu.pk)}},
                    },
                }
            },
        )

        # object created
        content = json.loads(response.content)
        attributes = content["data"]["attributes"]
        assert response.status_code == status.HTTP_201_CREATED
        job_instance = Job.objects.get(pk=attributes["uuid"])

        for index, reporting in enumerate(
            job_instance.reportings.order_by("created_at")
        ):
            assert (
                therapy_data["therapy"][index]["description"]
                == reporting.form_data["description"]
            )
            assert therapy_data["therapy"][index]["km"] == reporting.km
            assert therapy_data["therapy"][index]["end_km"] == reporting.end_km
            assert reporting.project_km == inspection.project_km
            assert reporting.project_end_km == inspection.project_end_km
            assert reporting.direction == inspection.direction
            assert reporting.lane == inspection.lane

        # Calculated fields are working properly

        assert attributes["reportingCount"] == 2

    def set_up_sheet_metadata(self) -> OccurrenceType:
        """
        Configure the metadata for the Company to allow testing of the sheet systems.

        NOTE: Due to the nature of the mapper we'll need to use certain IDs to make this work. If a test
        stops working, check if the IDs mentioned here were altered and no longer fit the required configuration.

        Returns:
            OccurrenceType: The sheet's OccurrenceType
        """

        # Add Inventory permissions
        false_permission(
            self.user, self.company, "Inventory", allowed="all", all_true=True
        )

        # Get the configured OccurrenceType
        occ_type = OccurrenceType.objects.get(
            uuid="006f411d-1388-49c5-989c-7e7447482ae9"
        )

        # Metadata config
        metadata = self.company.metadata
        metadata["sheet_inventory_occurrence_type"] = str(occ_type.pk)
        target = "1bb4364c-26b9-4b31-a7c1-e8d7876594fc"
        metadata["sheet_inventory_occurrence_type_mapper_for_inspection"] = [
            {
                "origin": "006f411d-1388-49c5-989c-7e7447482ae9",
                "target": target,
            },
            {
                "origin": "05e3967f-27b3-460d-94a5-d419c1588dce",
                "target": target,
            },
        ]
        self.company.metadata = metadata
        self.company.save()

        return occ_type

    def test_create_job_with_automatic_inventory_qs(self, client):
        """
        Ensure the creation of Reporting instances based on automatic Inventory queryset is working properly
        """

        occ_type = self.set_up_sheet_metadata()
        menu = RecordMenu.objects.first()

        # Create a Job but don't provide Inventory IDs, provide filters instead
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "filters": {
                            "occurrence_type": str(occ_type.pk),
                            "road_name": "BR101-SC",
                        },
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "menu": {"data": {"type": "RecordMenu", "id": str(menu.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)
        new_job_id = content["data"]["id"]
        new_job = Job.objects.get(pk=new_job_id)
        new_reps = new_job.reportings.all()

        # Call scheduled tasks manually
        process_job_async_batch()
        process_job_rep_in_rep_batches()

        # We'll need a new GET because the async data will not be yet included in the POST response
        # NOTE: The `while` is meant to simulate the long polling
        processing_async_creation = True
        while processing_async_creation:
            response = client.get(
                path="/{}/{}/?company={}".format(
                    self.model, new_job_id, str(self.company.pk)
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
                data={},
            )
            content = json.loads(response.content)
            attributes = content["data"]["attributes"]

            # Kill the loop when async task was done processing
            processing_async_creation = attributes["processingAsyncCreation"]

        # Both the parent AND child were created and added to the Job
        # This also means the calculated fields are working
        assert attributes["reportingCount"] == 2

        # Ensure a ReportingInReporting for the new Reporting instances was created
        rep_in_rep = ReportingInReporting.objects.filter(
            Q(parent=new_reps.first()) | Q(child=new_reps.first())
        )
        assert rep_in_rep.count() == 1

    def test_sheet_type_matches_all_provided_inventories(self, client):
        """
        Ensure that if an Inventory is provided with the sheet's OccurrenceType
        and other items are provided that don't match the OccurrenceType, the proper
        error will be returned.
        """

        EXPECTED_ERROR_MESSAGE = (
            "kartado.error.job.invalid_occurrence_type_in_async_creation"
        )

        sheet_type = self.set_up_sheet_metadata()

        # Get an Inventory that matches the sheet's type and one that doesn't
        matching_inventory = Reporting.objects.filter(
            occurrence_type=sheet_type
        ).first()
        non_matching_inventory = Reporting.objects.exclude(
            occurrence_type=sheet_type
        ).first()

        # Attempt to create the Job with those Inventory items
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "inventory": {
                            "data": [
                                {"type": "Inventory", "id": str(matching_inventory.pk)},
                                {
                                    "type": "Inventory",
                                    "id": str(non_matching_inventory.pk),
                                },
                            ]
                        },
                    },
                }
            },
        )

        assert (
            response.status_code == status.HTTP_400_BAD_REQUEST
        ), "Job creation should have been a 400 BAD REQUEST"

        content = json.loads(response.content)
        assert (
            content["errors"][0]["detail"] == EXPECTED_ERROR_MESSAGE
        ), "The incorrect type error message was not returned"

    def test_manual_inventory_works_when_using_metadata_sheet_occ_type(self, client):
        """
        Ensure the manual Inventory flow works with filter system if the provided Inventory
        items match the metadata's sheet type.
        """

        sheet_type = self.set_up_sheet_metadata()
        menu = RecordMenu.objects.first()

        # Get an Inventory that matches the sheet's type
        matching_inventory = Reporting.objects.filter(
            occurrence_type=sheet_type
        ).first()

        # Create the Job using only the Inventory found
        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "inventory": {
                            "data": [
                                {"type": "Inventory", "id": str(matching_inventory.pk)},
                            ]
                        },
                        "menu": {"data": {"type": "RecordMenu", "id": str(menu.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)
        new_job_id = content["data"]["id"]
        new_job = Job.objects.get(pk=new_job_id)
        new_reps = new_job.reportings.all()

        # Call scheduled task manually
        process_job_async_batch()
        process_job_rep_in_rep_batches()

        # We'll need a new GET because the async data will not be yet included in the POST response
        # NOTE: The `while` is meant to simulate the long polling
        processing_async_creation = True
        while processing_async_creation:
            response = client.get(
                path="/{}/{}/?company={}".format(
                    self.model, new_job_id, str(self.company.pk)
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
                data={},
            )
            content = json.loads(response.content)
            attributes = content["data"]["attributes"]

            # Kill the loop when async task was done processing
            processing_async_creation = attributes["processingAsyncCreation"]

        # Both the parent AND child were created and added to the Job
        # This also means the calculated fields are working
        assert attributes["reportingCount"] == 2

        # Ensure a ReportingInReporting for the new Reporting instances was created
        rep_in_rep = ReportingInReporting.objects.filter(
            Q(parent=new_reps.first()) | Q(child=new_reps.first())
        )
        assert rep_in_rep.count() == 1

    def test_update_job(self, client):
        reporting_base = Reporting.objects.filter(company=self.company)[0]

        reporting = Reporting.objects.create(
            company=self.company,
            occurrence_type=reporting_base.occurrence_type,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test",
        )

        job = Job.objects.filter(company=self.company)[0]

        occ_type = OccurrenceType.objects.filter(
            company=self.company,
            occurrence_kind="1",
            form_fields__fields__isnull=False,
        )[0]

        inventory = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="2"
        ).exclude(pk=reporting.pk)[0]

        menu = RecordMenu.objects.first()

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(job.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(job.pk),
                    "attributes": {
                        "metadata": {"test": "test"},
                        "reason": "testing",
                    },
                    "relationships": {
                        "reportings": {
                            "data": [{"type": "Reporting", "id": str(reporting.pk)}]
                        },
                        "inventory": {
                            "data": [{"type": "Inventory", "id": str(inventory.pk)}]
                        },
                        "occurrence_type": {
                            "data": [
                                {
                                    "type": "OccurrenceType",
                                    "id": str(occ_type.pk),
                                }
                            ]
                        },
                        "menu": {"data": {"type": "RecordMenu", "id": str(menu.pk)}},
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_job_with_reporting_with_job(self, client):
        job = Job.objects.filter(company=self.company)[0]

        reporting = Reporting.objects.filter(
            company=self.company, job__isnull=True
        ).exclude(occurrence_type__occurrence_kind="2")[0]

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(job.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(job.pk),
                    "attributes": {
                        "uuid": str(job.pk),
                        "metadata": {"test": "test"},
                    },
                    "relationships": {
                        "reportings": {
                            "data": [{"type": "Reporting", "id": str(reporting.pk)}]
                        }
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_job(self, client):
        job = Job.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(job.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_if_using_filters_field_provide_occurrence_type_filter(self, client):
        """
        Ensure Job creation using filters field requires at least the occurrence_type filter
        """

        EXPECTED_ERROR_MESSAGE = (
            "kartado.error.job.if_using_filters_field_provide_occurrence_type_filter"
        )

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "test",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "filters": {},
                    },
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

        assert (
            response.status_code == status.HTTP_400_BAD_REQUEST
        ), "Job creation should have been a 400 BAD REQUEST"

        content = json.loads(response.content)
        assert (
            content["errors"][0]["detail"] == EXPECTED_ERROR_MESSAGE
        ), "The missing filter error message was not returned"

    def test_check_async_creation(self, client):
        """
        Ensure /Job/<uuid>/CheckAsyncCreation is returning the correct data
        """

        job = Job.objects.first()

        response = client.get(
            path="/{}/{}/CheckAsyncCreation/?company={}".format(
                self.model, str(job.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)["data"]

        assert response.status_code == status.HTTP_200_OK, "Request was not successful"

        # Ensure the content is structured correctly
        assert content["type"] == "JobCheck", "Returned type was not JobCheck"
        assert content["attributes"]["uuid"] == str(job.pk), "Returned PK was incorrect"
        assert (
            content["attributes"]["processingAsyncCreation"] is False
        ), "Returned processing status was incorrect"

    def test_create_job_with_recuperation_items(self, client):
        inspection_occurrence_kind = get_obj_from_path(
            self.company.metadata, "inspection_occurrence_kind"
        )
        occ = OccurrenceType.objects.filter(
            occurrence_kind__in=inspection_occurrence_kind
        ).first()
        reporting_base = Reporting.objects.filter(company=self.company)[0]

        reporting = Reporting.objects.create(
            company=self.company,
            occurrence_type=occ,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test",
        )
        occ1 = OccurrenceType.objects.filter(company=self.company)[1]
        occ2 = OccurrenceType.objects.filter(company=self.company)[2]
        menu = RecordMenu.objects.first()

        new_form_data = {
            "therapy": [
                {"occurrence_type": "05e3967f-27b3-460d-94a5-d419c1588dce"},
                {"occurrence_type": "1bb4364c-26b9-4b31-a7c1-e8d7876594fc"},
            ]
        }

        occ_of_inspection = OccurrenceType.objects.filter(
            occurrence_kind__in=inspection_occurrence_kind
        ).first()
        reporting_with_therapy = Reporting.objects.create(
            company=self.company,
            occurrence_type=occ_of_inspection,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test1",
            form_data=new_form_data,
        )

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "Teste",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "reportings": {
                            "data": [
                                {"type": "Reporting", "id": str(reporting.pk)},
                                {
                                    "type": "Reporting",
                                    "id": str(reporting_with_therapy.pk),
                                },
                            ]
                        },
                        "recuperationOccurrenceTypes": {
                            "data": [
                                {
                                    "type": "OccurrenceType",
                                    "id": str(occ1.pk),
                                },
                                {
                                    "type": "OccurrenceType",
                                    "id": str(occ2.pk),
                                },
                            ]
                        },
                        "menu": {"data": {"type": "RecordMenu", "id": str(menu.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)
        attributes = content["data"]["attributes"]
        relationships = content["data"]["relationships"]

        assert attributes["reportingCount"] == 4

        # Ensure the new Reporting instances are related to the menu
        new_reps_ids = [item["id"] for item in relationships["reportings"]["data"]]
        new_reps = Reporting.objects.filter(pk__in=new_reps_ids)
        for rep in new_reps:
            assert rep.menu == menu

    def test_create_job_with_recuperation_items_requires_menu(self, client):
        reporting_base = Reporting.objects.filter(company=self.company)[0]

        reporting = Reporting.objects.create(
            company=self.company,
            occurrence_type=reporting_base.occurrence_type,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test",
        )
        occ1 = OccurrenceType.objects.filter(company=self.company)[1]
        occ2 = OccurrenceType.objects.filter(company=self.company)[2]

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "Teste",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "reportings": {
                            "data": [{"type": "Reporting", "id": str(reporting.pk)}]
                        },
                        "recuperationOccurrenceTypes": {
                            "data": [
                                {
                                    "type": "OccurrenceType",
                                    "id": str(occ1.pk),
                                },
                                {
                                    "type": "OccurrenceType",
                                    "id": str(occ2.pk),
                                },
                            ]
                        }
                        # Menu relationship omitted
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_job_notes(self, client, enable_unaccent):
        reporting_base = Reporting.objects.filter(company=self.company)[0]
        form_data = {"notes": "Aéióu"}

        job = Job.objects.filter(company=self.company).first()

        Reporting.objects.create(
            company=self.company,
            occurrence_type=reporting_base.occurrence_type,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test",
            form_data=form_data,
            job=job,
        )

        response = client.get(
            path="/{}/?company={}&notes={}".format(
                self.model, str(self.company.pk), "eiou"
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        assert content["meta"]["pagination"]["count"] > 0

    def test_get_job_occurrence_type(self, client):
        reporting_base = Reporting.objects.filter(company=self.company)[0]
        occurrence_type = reporting_base.occurrence_type
        if occurrence_type.previous_version is None:
            previous_occt = OccurrenceType.objects.filter(company=self.company).exclude(
                uuid=occurrence_type.uuid
            )[0]
            occurrence_type.previous_version = previous_occt
            occurrence_type.save()
        job = Job.objects.filter(company=self.company).first()

        Reporting.objects.create(
            company=self.company,
            occurrence_type=occurrence_type,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test",
            job=job,
        )

        response = client.get(
            path="/{}/?company={}&occurrence_type={}".format(
                self.model, str(self.company.pk), str(occurrence_type.uuid)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        assert content["meta"]["pagination"]["count"] > 0

    def test_get_job_occurrence_kind(self, client):
        reporting_base = Reporting.objects.filter(company=self.company)[0]
        occurrence_type = reporting_base.occurrence_type
        job = Job.objects.filter(company=self.company).first()

        Reporting.objects.create(
            company=self.company,
            occurrence_type=occurrence_type,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test",
            job=job,
        )

        response = client.get(
            path="/{}/?company={}&occurrence_kind={}".format(
                self.model, str(self.company.pk), occurrence_type.occurrence_kind
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        assert content["meta"]["pagination"]["count"] > 0

    def test_sync_info_success(self, client):
        """Test SyncInfo endpoint with required parameters."""

        jobs_rdos_user_firms = "5|something"
        response = client.get(
            path="/{}/SyncInfo/?company={}&jobs_rdos_user_firms={}".format(
                self.model, str(self.company.pk), jobs_rdos_user_firms
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK

    def test_sync_info_missing_jobs_section(self, client):
        """Test SyncInfo endpoint with missing jobs_rdos_user_firms param."""

        response = client.get(
            path="/{}/SyncInfo/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        assert content == {"data": {}}

    def test_sync_info_missing_force_sync_jobs_ids(self, client):
        """Test SyncInfo endpoint response with missing force_sync_jobs_ids param."""
        jobs_rdos_user_firms = "5|something"
        response = client.get(
            path="/{}/SyncInfo/?company={}&jobs_rdos_user_firms={}".format(
                self.model, str(self.company.pk), jobs_rdos_user_firms
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["data"]["force_sync_jobs_total"] == 0
        assert content["data"]["force_sync_reportings_total"] == 0
        assert content["data"]["force_sync_reportings_files_total"] == 0

    def test_sync_info_mobile_sync_not_found(self, client):
        """Test SyncInfo endpoint with non-existent mobile_sync_id."""
        # Create a job for the company

        jobs_rdos_user_firms = "5|something"
        response = client.get(
            path="/{}/SyncInfo/?company={}&jobs_rdos_user_firms={}&mobile_sync_id=0000000-0000-0000-0000-000000000000".format(
                self.model, str(self.company.pk), jobs_rdos_user_firms
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_sync_info_with_valid_mobile_sync(self, client):
        """Test SyncInfo endpoint with a valid mobile_sync_id."""
        # Create a job for the company

        mobile_sync = MobileSync.objects.create(company=self.company)

        jobs_rdos_user_firms = "5|something"
        response = client.get(
            path="/{}/SyncInfo/?company={}&jobs_rdos_user_firms={}&mobile_sync_id={}".format(
                self.model,
                str(self.company.pk),
                jobs_rdos_user_firms,
                str(mobile_sync.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )
        assert response.status_code == status.HTTP_200_OK

    def test_archive_job(self, client):
        """Test BulkArchive endpoint with archive, unarchive and report removal."""
        # Get jobs from fixture to archive/unarchive
        job_to_archive = Job.objects.filter(archived=False).first()  # not archived
        job_to_unarchive = Job.objects.filter(archived=True).first()  # archived

        # Create a reporting with unexecuted status for testing removal

        reporting_status = ServiceOrderActionStatus.objects.filter(
            companies=self.company, status_specs__order__lt=3
        ).first()

        _ = Reporting.objects.create(
            company=self.company,
            job=job_to_archive,
            status=reporting_status,
            number="test-bulk-archive",
            km=0,
            direction="x",
            lane="x",
        )

        response = client.post(
            path=f"/{self.model}/BulkArchive/?company={self.company.pk}",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {self.token}",
            data={
                "data": {
                    "archiveJobs": [str(job_to_archive.pk)],
                    "unarchiveJobs": [str(job_to_unarchive.pk)],
                    "removeUnexecutedReportings": True,
                }
            },
        )

        assert response.status_code == status.HTTP_200_OK

        # Verify job states changed
        job_to_archive.refresh_from_db()
        job_to_unarchive.refresh_from_db()

        assert job_to_archive.archived is True
        assert job_to_unarchive.archived is False

    def test_create_job_with_recuperation_items_no_recuperation_occ(self, client):
        inspection_occurrence_kind = get_obj_from_path(
            self.company.metadata, "inspection_occurrence_kind"
        )
        reporting_base = Reporting.objects.filter(company=self.company)[0]
        menu = RecordMenu.objects.first()

        new_form_data = {
            "therapy": [
                {"occurrence_type": "05e3967f-27b3-460d-94a5-d419c1588dce"},
                {"occurrence_type": "1bb4364c-26b9-4b31-a7c1-e8d7876594fc"},
            ]
        }

        occ_of_inspection = OccurrenceType.objects.filter(
            occurrence_kind__in=inspection_occurrence_kind
        ).first()
        reporting_with_therapy = Reporting.objects.create(
            company=self.company,
            occurrence_type=occ_of_inspection,
            km=reporting_base.km,
            status=reporting_base.status,
            number="test1",
            form_data=new_form_data,
        )

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "title": "Teste",
                        "startDate": datetime.now().replace(microsecond=0).isoformat(),
                        "isRecuperationFlow": True,
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "reportings": {
                            "data": [
                                {
                                    "type": "Reporting",
                                    "id": str(reporting_with_therapy.pk),
                                },
                            ]
                        },
                        "menu": {"data": {"type": "RecordMenu", "id": str(menu.pk)}},
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        content = json.loads(response.content)
        attributes = content["data"]["attributes"]

        assert attributes["reportingCount"] == 2

    def test_create_job_with_inventory_in_reportings_fails(self, client):
        """
        Ensure that creating a job with inventory (occurrence_kind=2) in
        reportings list raises validation error
        """
        inventory = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="2"
        ).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=json.dumps(
                {
                    "data": {
                        "type": self.model,
                        "attributes": {
                            "title": "Test Job with Inventory",
                            "startDate": str(datetime.now()),
                        },
                        "relationships": {
                            "company": {
                                "data": {"type": "Company", "id": str(self.company.pk)}
                            },
                            "reportings": {
                                "data": [{"type": "Reporting", "id": str(inventory.pk)}]
                            },
                        },
                    }
                }
            ),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert "kartado.error.inventory_in_job_exception" in str(content)

    def test_patch_job_with_inventory_in_add_reportings_fails(self, client):
        """
        Ensure that patching a job with inventory (occurrence_kind=2) in
        add_reportings list raises validation error
        """
        job = Job.objects.filter(company=self.company).first()
        inventory = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="2"
        ).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(job.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data=json.dumps(
                {
                    "data": {
                        "type": self.model,
                        "id": str(job.pk),
                        "attributes": {},
                        "relationships": {
                            "company": {
                                "data": {"type": "Company", "id": str(self.company.pk)}
                            },
                            "addReportings": {
                                "data": [{"type": "Reporting", "id": str(inventory.pk)}]
                            },
                        },
                    }
                }
            ),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert "kartado.error.inventory_in_job_exception" in str(content)
