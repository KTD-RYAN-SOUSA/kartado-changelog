import json
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from helpers.testing.fixtures import TestBase, false_permission

from ..models import Construction
from ..serializers import ConstructionSerializer

pytestmark = pytest.mark.django_db


class TestConstruction(TestBase):
    model = "Construction"

    ATTRIBUTES = {
        "name": "Construction Test",
        "description": "Construction Test Description",
        "location": "Construction Location",
        "km": 123.1,
        "end_km": 124.6,
        "construction_item": "Construction Item",
        "intervention_type": "1",
        "schedulingStartDate": "2021-05-13T09:22:51-03:00",
        "schedulingEndDate": "2021-05-13T09:22:55-03:00",
        "analysisStartDate": "2021-05-13T09:22:58-03:00",
        "analysisEndDate": "2021-05-13T09:23:53-03:00",
        "executionStartDate": "2021-05-13T09:23:56-03:00",
        "executionEndDate": "2021-05-13T09:23:58-03:00",
        "spendScheduleStartDate": "2021-05-13T09:24:01-03:00",
        "spendScheduleEndDate": "2021-05-13T09:24:03-03:00",
    }

    def test_construction_list(self, client):
        """
        Ensures we can list using the Construction endpoint
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

    def test_list_construction_without_company(self, client):
        """
        Ensures calling the Construction endpoint without a company
        results in 403 Forbidden
        """

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_construction(self, client):
        """
        Ensures a specific Construction can be fetched using the uuid
        """

        instance = Construction.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK

    def test_create_construction(self, client):
        """
        Ensures a new Construction can be created using the endpoint
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
                        }
                    },
                }
            },
        )

        # Object was created successfully
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_construction_without_company_id(self, client):
        """
        Ensures a new Construction cannot be created without a company id
        """

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {"type": self.model, "attributes": self.ATTRIBUTES}},
        )

        # Request is forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_construction_without_permission(self, client):
        """
        Ensures a new Construction cannot be created without
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

    def test_update_construction(self, client):
        """
        Ensure a Construction can be updated using the endpoint
        """

        instance = Construction.objects.filter(company=self.company).first()

        # Change name from "Construction Test" to "Construction Update"
        self.ATTRIBUTES["name"] = "Construction Update"

        response = client.patch(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(instance.pk),
                    "attributes": self.ATTRIBUTES,
                }
            },
        )

        # The object has changed
        assert response.status_code == status.HTTP_200_OK

        # Reset name to "Construction Test"
        self.ATTRIBUTES["name"] = "Construction Test"

    def test_delete_construction(self, client):
        """
        Ensure a Construction can be deleted using the endpoint
        """

        instance = Construction.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/?company={}".format(
                self.model, str(instance.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # Object was deleted
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_calculate_month_schedule_empty(self):
        """Returns empty dict when schedule, phases or progresses are missing."""
        instance = Construction.objects.filter(company=self.company).first()
        # Ensure empty relevant fields
        instance.spend_schedule = {}
        instance.phases = []
        instance.save(update_fields=["spend_schedule", "phases"])

        serializer = ConstructionSerializer()
        result = serializer.calculate_month_schedule(instance)
        assert result == {}

    def test_calculate_month_schedule_current_month_with_progress(self):
        """Calculates expected/executed for current month with simple single subphase."""
        now = timezone.now()
        current_key = now.strftime("%m/%Y")

        instance = Construction.objects.filter(company=self.company).first()
        instance.phases = [
            {
                "weight": 100,
                "subphases": [
                    {
                        "weight": 100,
                        "expectedAmount": 100,
                        "unit": "u",
                        "subphaseDescription": "s0",
                    }
                ],
            }
        ]
        instance.spend_schedule = {current_key: "0.25"}
        instance.save(update_fields=["phases", "spend_schedule"])

        instance.construction_progresses.create(
            name="p1",
            executed_at=now,
            created_by=self.user,
            progress_details=[{"phase": 0, "subphase": 0, "executedAmount": 30}],
        )

        serializer = ConstructionSerializer()
        result = serializer.calculate_month_schedule(instance)

        # executed: (30/100) * 1.0 (weights 100% * 100%) = 0.3
        # expected_month: 0.25 (from string)
        # expected (cumulative) == 0.25
        assert result["expected_month"] == 0.25
        assert result["executed_month"] == pytest.approx(0.3)
        assert result["executed"] == pytest.approx(0.3)
        assert result["expected"] == pytest.approx(0.25)

    def test_calculate_month_schedule_prev_copy_and_diff(self):
        now = timezone.now()
        prev = now - timedelta(days=31)
        current_key = now.strftime("%m/%Y")
        prev_key = prev.strftime("%m/%Y")

        instance = Construction.objects.filter(company=self.company).first()
        instance.phases = [
            {
                "weight": 100,
                "subphases": [
                    {
                        "weight": 100,
                        "expectedAmount": 100,
                        "unit": "u",
                        "subphaseDescription": "s0",
                    }
                ],
            }
        ]
        # Two in schedule, ordered by serializer logic
        instance.spend_schedule = {prev_key: "0.25", current_key: "0.25"}
        instance.save(update_fields=["phases", "spend_schedule"])

        # Progress only on previous: executedAmount = 50 -> executed total = 0.5
        instance.construction_progresses.create(
            name="p_prev",
            executed_at=prev,
            created_by=self.user,
            progress_details=[{"phase": 0, "subphase": 0, "executedAmount": 50}],
        )

        serializer = ConstructionSerializer()
        result = serializer.calculate_month_schedule(instance)

        # For current, with no progress, executed copies previous (0.5)
        assert result["expected_month"] == 0.25
        assert result["executed"] == pytest.approx(0.5)
        # executed_month is diff from previous executed (0.5 - 0.5) = 0
        assert result["executed_month"] == pytest.approx(0.0)
        # cumulative expected is 0.25 (prev) + 0.25 (current) = 0.5
        assert result["expected"] == pytest.approx(0.5)

    def test_get_executed_in_month_when_present(self):
        """get_executed_in_month returns executed_month when present in month_schedule."""
        now = timezone.now()
        current_key = now.strftime("%m/%Y")

        instance = Construction.objects.filter(company=self.company).first()
        instance.phases = [
            {
                "weight": 100,
                "subphases": [
                    {
                        "weight": 100,
                        "expectedAmount": 100,
                        "unit": "u",
                        "subphaseDescription": "s0",
                    }
                ],
            }
        ]
        instance.spend_schedule = {current_key: "0.25"}
        instance.save(update_fields=["phases", "spend_schedule"])

        # Progress this month: executedAmount = 30 -> executed total = 0.3
        instance.construction_progresses.create(
            name="p1",
            executed_at=now,
            created_by=self.user,
            progress_details=[{"phase": 0, "subphase": 0, "executedAmount": 30}],
        )

        serializer = ConstructionSerializer()
        executed_in_month = serializer.get_executed_in_month(instance)
        assert executed_in_month == pytest.approx(0.3)

    def test_get_current_total_when_present(self):
        """get_current_total returns executed when present in month_schedule."""
        now = timezone.now()
        current_key = now.strftime("%m/%Y")

        instance = Construction.objects.filter(company=self.company).first()
        instance.phases = [
            {
                "weight": 100,
                "subphases": [
                    {
                        "weight": 100,
                        "expectedAmount": 100,
                        "unit": "u",
                        "subphaseDescription": "s0",
                    }
                ],
            }
        ]
        instance.spend_schedule = {current_key: "0.25"}
        instance.save(update_fields=["phases", "spend_schedule"])

        # Progress this month: executedAmount = 40 -> executed total = 0.4
        instance.construction_progresses.create(
            name="p1",
            executed_at=now,
            created_by=self.user,
            progress_details=[{"phase": 0, "subphase": 0, "executedAmount": 40}],
        )

        serializer = ConstructionSerializer()
        current_total = serializer.get_current_total(instance)
        assert current_total == pytest.approx(0.4)

    def _setup_simple_construction(self, expected_month_str, executed_amount):
        now = timezone.now()
        current_key = now.strftime("%m/%Y")

        instance = Construction.objects.filter(company=self.company).first()
        instance.phases = [
            {
                "weight": 100,
                "subphases": [
                    {
                        "weight": 100,
                        "expectedAmount": 100,
                        "unit": "u",
                        "subphaseDescription": "s0",
                    }
                ],
            }
        ]
        instance.spend_schedule = {current_key: expected_month_str}
        instance.save(update_fields=["phases", "spend_schedule"])

        if executed_amount is not None:
            instance.construction_progresses.create(
                name="p1",
                executed_at=now,
                created_by=self.user,
                progress_details=[
                    {"phase": 0, "subphase": 0, "executedAmount": executed_amount}
                ],
            )
        return instance

    def test_get_construction_rate_regular(self):
        """executed_month >= expected_month -> regular"""
        # expected_month: 0.25, executed_month: 0.3 (30/100)
        instance = self._setup_simple_construction("0.25", 30)
        serializer = ConstructionSerializer()
        assert serializer.get_construction_rate(instance) == "regular"

    def test_get_construction_rate_stuck(self):
        """executed_month == 0.0 -> stuck"""
        # expected_month: 0.25, executed_month: 0.0
        instance = self._setup_simple_construction("0.25", None)
        serializer = ConstructionSerializer()
        assert serializer.get_construction_rate(instance) == "stuck"

    def test_get_construction_rate_slow(self):
        """executed_month < expected_month and executed_month > 0 -> slow"""
        # expected_month: 0.5, executed_month: 0.3
        instance = self._setup_simple_construction("0.5", 30)
        serializer = ConstructionSerializer()
        assert serializer.get_construction_rate(instance) == "slow"

    def test_validate_construction(self, client):
        """
        Ensures end dates can't be sooner than start dates
        """

        # Backup values for a reset after the test
        old_scheduling_start_date = self.ATTRIBUTES["schedulingStartDate"]
        old_scheduling_end_date = self.ATTRIBUTES["schedulingEndDate"]

        # Set invalid dates (start is a minute after end)
        self.ATTRIBUTES["schedulingStartDate"] = "2021-05-13T09:23:51-03:00"
        self.ATTRIBUTES["schedulingEndDate"] = "2021-05-13T09:22:51-03:00"

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
            "scheduling_end_date deve ser maior que scheduling_start_date"
        )
        assert content["errors"][0]["detail"] == expected_message

        # Reset changed values
        self.ATTRIBUTES["schedulingStartDate"] = old_scheduling_start_date
        self.ATTRIBUTES["schedulingEndDate"] = old_scheduling_end_date

    def test_validade_followup_data(self, client):

        EXPECTED_RESPONSE = {
            "data": [
                {
                    "weight": 50,
                    "subphases": [
                        {
                            "unit": "unidade",
                            "weight": 100,
                            "expectedAmount": 50,
                            "subphaseDescription": "9",
                            "executedAmount": 12,
                            "percentageDone": 0.24,
                            "straightLineDiagram": [],
                        }
                    ],
                    "responsible": "teste",
                    "phaseDescription": "3",
                },
                {
                    "weight": 50,
                    "subphases": [
                        {
                            "unit": "m2",
                            "weight": 100,
                            "expectedAmount": 20,
                            "subphaseDescription": "8",
                            "executedAmount": 8,
                            "percentageDone": 0.4,
                            "straightLineDiagram": [],
                        }
                    ],
                    "responsible": "teste",
                    "phaseDescription": "7",
                },
            ]
        }

        construction_instance = Construction.objects.filter(
            name="Teste follow up endpoint"
        ).first()
        construction_progress_instance = (
            construction_instance.construction_progresses.first()
        )

        response = client.get(
            path="/{}/{}/FollowUp/?company={}&construction_progres={}".format(
                self.model,
                str(construction_instance.pk),
                str(self.company.pk),
                str(construction_progress_instance.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)
        for index, data in enumerate(EXPECTED_RESPONSE["data"]):
            assert data == content["data"][index]

        # Object was fetched successfully
        assert response.status_code == status.HTTP_200_OK
