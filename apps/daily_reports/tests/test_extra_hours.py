import json
from unittest.mock import patch

import pytest
from rest_framework import status

from apps.resources.models import ContractPeriod
from helpers.extra_hours import calculate_extra_hours_worker
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


# ============================================================
# Unit tests for calculate_extra_hours_worker
# ============================================================

STANDARD_SCHEDULES = [
    {
        "start_time": "07:30",
        "end_time": "12:00",
        "days_of_week": [1, 2, 3, 4, 5],
        "period": "morning",
    },
    {
        "start_time": "13:00",
        "end_time": "17:18",
        "days_of_week": [1, 2, 3, 4, 5],
        "period": "afternoon",
    },
]


class TestCalculateExtraHoursWorkerBasic:
    """Testes básicos adaptados da lógica anterior para a nova função."""

    def test_compensation_with_early_start(self):
        """
        RN32: compensation mode, worked early (06:00-11:00), planned 07:30-12:00 + 13:00-17:18.
        Early extra: 06:00-07:30 = 90min = 1h30 compensation.
        No extras, no absence.
        """
        item = {"morningStart": "06:00", "morningEnd": "11:00"}
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=1,
            is_holiday=False,
            is_compensation=True,
        )
        assert result["compensation"] == "01:30"
        assert result["extra_hours_50_day"] == "00:00"
        assert result["extra_hours_50_night"] == "00:00"
        assert result["extra_hours_100_day"] == "00:00"
        assert result["extra_hours_100_night"] == "00:00"
        assert result["absence"] == "00:00"

    def test_compensation_with_surplus(self):
        """
        RN32: compensation mode, worked more than planned.
        Planned: 270+258=528min=8h48. Worked: 06:30-12:00=330min + 13:00-19:18=378min=708min.
        Surplus = 708-528 = 180min = 3h00.
        """
        item = {
            "morningStart": "06:30",
            "morningEnd": "12:00",
            "afternoonStart": "13:00",
            "afternoonEnd": "19:18",
        }
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=1,
            is_holiday=False,
            is_compensation=True,
        )
        assert result["compensation"] == "03:00"
        assert result["extra_hours_50_day"] == "00:00"
        assert result["extra_hours_50_night"] == "00:00"
        assert result["absence"] == "00:00"

    def test_compensation_on_holiday_all_worked_becomes_compensation(self):
        """
        RN32 + RN35/RN36: holiday + compensation mode.
        All worked hours become compensation regardless of planned schedule.
        Worked: 08:00-12:00 = 4h. Compensation = 4h.
        """
        item = {"morningStart": "07:00", "morningEnd": "12:00"}
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=3,
            is_holiday=True,
            is_compensation=True,
        )
        assert result["compensation"] == "05:00"
        assert result["extra_hours_100_day"] == "00:00"
        assert result["extra_hours_50_day"] == "00:00"
        assert result["absence"] == "00:00"

    def test_extra_hours_50_weekday_excess(self):
        """
        Contract 7:30-12:00, 13:00-17:18 (Mon-Fri).
        Worked 6:30-12:00, 13:00-18:18. Excess = 2h, entirely daytime.
        """
        item = {
            "morningStart": "06:30",
            "morningEnd": "12:00",
            "afternoonStart": "13:00",
            "afternoonEnd": "18:18",
        }
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_50_day"] == "02:00"
        assert result["extra_hours_50_night"] == "00:00"
        assert result["extra_hours_100_day"] == "00:00"
        assert result["absence"] == "00:00"

    def test_extra_hours_100_sunday(self):
        """
        Contract 7:30-12:00, 13:00-17:18 (Mon-Fri, not Sunday).
        Worked 7:30-12:00, 13:00-17:18 on Sunday -> all 8h48 = 100% daytime.
        """
        item = {
            "morningStart": "07:30",
            "morningEnd": "12:00",
            "afternoonStart": "13:00",
            "afternoonEnd": "17:18",
        }
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=7,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_100_day"] == "08:48"
        assert result["extra_hours_100_night"] == "00:00"
        assert result["extra_hours_50_day"] == "00:00"
        assert result["absence"] == "00:00"

    def test_extra_hours_100_holiday(self):
        """Holiday on a weekday: all worked hours = 100% daytime."""
        item = {
            "morningStart": "08:30",
            "morningEnd": "12:00",
            "afternoonStart": "13:00",
            "afternoonEnd": "17:18",
        }
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=3,
            is_holiday=True,
            is_compensation=False,
        )
        assert result["extra_hours_100_day"] == "07:48"
        assert result["extra_hours_100_night"] == "00:00"
        assert result["extra_hours_50_day"] == "00:00"
        assert result["absence"] == "00:00"

    def test_extra_hours_split_day_night(self):
        """
        Contract 7:30-12:00, 13:00-17:18 (Mon-Fri), no planned night period.
        Worked 21:30-00:00 on Monday (unplanned night period).
        21:30-22:00 = 30min daytime (50%), 22:00-00:00 = 120min nighttime (50%).
        """
        item = {"nightStart": "21:30", "nightEnd": "00:00"}
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_50_day"] == "00:30"
        assert result["extra_hours_50_night"] == "02:00"
        assert result["extra_hours_100_day"] == "00:00"

    def test_absence(self):
        """
        Contract 7:30-12:00, 13:00-17:18 (Mon-Fri).
        Worked 8:30-12:00, 14:00-17:18. Deficit = 2h.
        """
        item = {
            "morningStart": "08:30",
            "morningEnd": "12:00",
            "afternoonStart": "14:00",
            "afternoonEnd": "17:18",
        }
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["absence"] == "02:00"
        assert result["extra_hours_50_day"] == "00:00"

    def test_no_absence_on_non_planned_day(self):
        """Saturday not in contract days_of_week: no absence."""
        result = calculate_extra_hours_worker(
            {},
            STANDARD_SCHEDULES,
            day_of_week=6,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["absence"] == "00:00"

    def test_all_hours_50_on_unplanned_weekday(self):
        """Saturday not in contract -> all worked hours are 50% (daytime)."""
        item = {"morningStart": "08:00", "morningEnd": "12:00"}
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=6,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_50_day"] == "04:00"
        assert result["extra_hours_50_night"] == "00:00"
        assert result["absence"] == "00:00"

    def test_exact_planned_hours_no_extras_no_absence(self):
        """Working exactly the planned hours: all zeros."""
        item = {
            "morningStart": "07:30",
            "morningEnd": "12:00",
            "afternoonStart": "13:00",
            "afternoonEnd": "17:18",
        }
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_50_day"] == "00:00"
        assert result["extra_hours_50_night"] == "00:00"
        assert result["extra_hours_100_day"] == "00:00"
        assert result["extra_hours_100_night"] == "00:00"
        assert result["absence"] == "00:00"

    def test_deleted_period_is_ignored(self):
        """Periods marked as deleted are ignored."""
        item = {
            "morningStart": "06:00",
            "morningEnd": "12:00",
            "morningStartIsDeleted": True,
            "afternoonStart": "13:00",
            "afternoonEnd": "17:18",
        }
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        # Only afternoon worked (258min). Planned = 270+258=528min. Absence = 270min = 4h30.
        assert result["absence"] == "04:30"
        assert result["extra_hours_50_day"] == "00:00"

    def test_no_extra_when_worked_within_night_schedule(self):
        """
        Worker with planned night schedule 22:00-05:00.
        Worked 22:00-02:00 (within planned): no extras, 3h absence (02:00-05:00).
        """
        night_schedules = [
            {
                "start_time": "22:00",
                "end_time": "05:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "night",
            }
        ]
        item = {"nightStart": "22:00", "nightEnd": "02:00"}
        result = calculate_extra_hours_worker(
            item,
            night_schedules,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_50_night"] == "00:00"
        assert result["extra_hours_50_day"] == "00:00"
        assert result["absence"] == "03:00"

    def test_empty_extra_hours_on_planned_day_generates_full_absence(self):
        """No worked hours on a planned day -> full absence."""
        result = calculate_extra_hours_worker(
            {},
            STANDARD_SCHEDULES,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        # Planned: 270 + 258 = 528min = 8h48
        assert result["absence"] == "08:48"

    def test_absence_on_sunday_with_planned_schedule(self):
        """
        Sunday with planned contract. Worker arrived 30min late and left 1h after planned end.
        Planned: 07:30-12:00 (4h30). Worked: 08:00-13:00 (5h).
        Overlap: 08:00-12:00 = 4h (normal).
        Absence: 07:30-08:00 = 30min.
        Extra 100% day: 12:00-13:00 = 1h.
        """
        sunday_schedules = [
            {
                "start_time": "07:30",
                "end_time": "12:00",
                "days_of_week": [7],
                "period": "morning",
            }
        ]
        item = {"morningStart": "08:00", "morningEnd": "13:00"}
        result = calculate_extra_hours_worker(
            item,
            sunday_schedules,
            day_of_week=7,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["absence"] == "00:30"
        assert result["extra_hours_100_day"] == "01:00"
        assert result["extra_hours_50_day"] == "00:00"

    def test_no_absence_on_sunday_without_planned_schedule(self):
        """
        Sunday not in contract days_of_week. Worker shows up anyway.
        All worked hours = 100% extra, no absence.
        """
        item = {"morningStart": "08:00", "morningEnd": "12:00"}
        result = calculate_extra_hours_worker(
            item,
            STANDARD_SCHEDULES,  # Mon-Fri only
            day_of_week=7,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_100_day"] == "04:00"
        assert result["absence"] == "00:00"
        assert result["extra_hours_50_day"] == "00:00"

    def test_no_absence_on_holiday_even_with_planned_schedule(self):
        """
        Holiday with planned contract but worker didn't show: no absence on holidays.
        """
        holiday_schedules = [
            {
                "start_time": "07:30",
                "end_time": "12:00",
                "days_of_week": [3],
                "period": "morning",
            }
        ]
        result = calculate_extra_hours_worker(
            {},
            holiday_schedules,
            day_of_week=3,
            is_holiday=True,
            is_compensation=False,
        )
        assert result["absence"] == "00:00"
        assert result["extra_hours_100_day"] == "00:00"

    def test_different_periods(self):
        """Worked afternoon, planned only morning: 4h extra 50% day + 4h absence."""
        schedules = [
            {
                "start_time": "08:00",
                "end_time": "12:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            }
        ]
        item = {"afternoonStart": "13:00", "afternoonEnd": "17:00"}
        result = calculate_extra_hours_worker(
            item,
            schedules,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_50_day"] == "04:00"
        assert result["absence"] == "04:00"

    def test_multiple_planned_intervals_same_period(self):
        """Two planned blocks in morning; worked 08:00-12:00 covers both + gaps."""
        schedules = [
            {
                "start_time": "08:00",
                "end_time": "09:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            },
            {
                "start_time": "10:00",
                "end_time": "11:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            },
        ]
        item = {
            "morningStart": "08:00",
            "morningEnd": "12:00",
            "afternoonStart": "13:00",
            "afternoonEnd": "17:00",
        }
        result = calculate_extra_hours_worker(
            item,
            schedules,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_50_day"] == "06:00"
        assert result["absence"] == "00:00"

    def test_multiple_planned_intervals_with_absence(self):
        """Two planned blocks in morning; worked only until 10:00 -> 1h absence."""
        schedules = [
            {
                "start_time": "08:00",
                "end_time": "09:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            },
            {
                "start_time": "10:00",
                "end_time": "11:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            },
        ]
        item = {
            "morningStart": "08:00",
            "morningEnd": "10:00",
            "afternoonStart": "13:00",
            "afternoonEnd": "17:00",
        }
        result = calculate_extra_hours_worker(
            item,
            schedules,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_50_day"] == "05:00"
        assert result["absence"] == "01:00"

    def test_all_periods_with_night_schedule(self):
        """
        All three periods worked. Contract has night schedule so worked night
        hours within plan are NOT extra. Total extra = 3h30 day + 1h30 night.
        """
        schedules = [
            {
                "start_time": "07:00",
                "end_time": "09:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            },
            {
                "start_time": "10:00",
                "end_time": "12:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            },
            {
                "start_time": "13:00",
                "end_time": "15:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "afternoon",
            },
            {
                "start_time": "16:00",
                "end_time": "17:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "afternoon",
            },
            {
                "start_time": "22:00",
                "end_time": "23:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "night",
            },
            {
                "start_time": "23:30",
                "end_time": "01:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "night",
            },
        ]
        item = {
            "morningStart": "06:00",
            "morningEnd": "11:00",
            "afternoonStart": "13:00",
            "afternoonEnd": "17:30",
            "nightStart": "22:00",
            "nightEnd": "02:00",
        }
        result = calculate_extra_hours_worker(
            item,
            schedules,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        # Morning extra: 06:00-07:00 (1h) + 09:00-10:00 (1h) + 11:00 (1h gap) = 2h day
        # Afternoon extra: 17:00-17:30 = 30min day
        # Correction: morning 06:00-11:00=5h worked, planned 07:00-09:00+10:00-12:00=4h,
        #   overlap=07:00-09:00(2h)+10:00-11:00(1h)=3h, extra=2h day
        # Afternoon 13:00-17:30=4h30, planned 13:00-15:00+16:00-17:00=3h,
        #   overlap=13:00-15:00(2h)+16:00-17:00(1h)=3h, extra=1h30 day
        # Night 22:00-02:00=4h, planned 22:00-23:00+23:30-01:00=2h30,
        #   overlap=2h30 night, extra=1h30 night
        # Absence: morning planned 4h - overlap 3h = 1h
        assert result["extra_hours_50_day"] == "03:30"
        assert result["extra_hours_50_night"] == "01:30"
        assert result["absence"] == "01:00"
        assert result["extra_hours_100_day"] == "00:00"

    def test_all_periods_without_night_schedule(self):
        """
        No planned night in contract; worked night period is unplanned extra.
        Night extra: 22:00-02:00 = 4h (all night, 50%).
        """
        schedules = [
            {
                "start_time": "07:00",
                "end_time": "09:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            },
            {
                "start_time": "10:00",
                "end_time": "12:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "morning",
            },
            {
                "start_time": "13:00",
                "end_time": "15:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "afternoon",
            },
            {
                "start_time": "16:00",
                "end_time": "17:00",
                "days_of_week": [1, 2, 3, 4, 5],
                "period": "afternoon",
            },
        ]
        item = {
            "morningStart": "06:00",
            "morningEnd": "11:00",
            "afternoonStart": "13:00",
            "afternoonEnd": "17:30",
            "nightStart": "22:00",
            "nightEnd": "02:00",
        }
        result = calculate_extra_hours_worker(
            item,
            schedules,
            day_of_week=1,
            is_holiday=False,
            is_compensation=False,
        )
        assert result["extra_hours_50_day"] == "03:30"
        assert result["extra_hours_50_night"] == "04:00"
        assert result["absence"] == "01:00"
        assert result["extra_hours_100_day"] == "00:00"


WORKER_SCHEDULES = [
    {
        "start_time": "07:30",
        "end_time": "12:00",
        "days_of_week": [1, 2, 3, 4, 5],
        "period": "morning",
    },
    {
        "start_time": "13:00",
        "end_time": "17:18",
        "days_of_week": [1, 2, 3, 4, 5],
        "period": "afternoon",
    },
]


# ============================================================
# Integration tests for RecalculateExtraHoursView endpoint
# ============================================================


class TestRecalculateExtraHoursEndpoint(TestBase):
    model = "MultipleDailyReport"

    MDR_UUID = "0a2daca5-416e-4679-bb59-af8fe1801bba"
    MDR_CONTRACT = "339fc8c2-3351-4509-af8a-aa7c519d89ee"
    MDR_FIRM = "eb093034-7f05-4d93-8a7d-cdf8ee04923d"

    @pytest.fixture(autouse=True)
    def setup_contract_period(self):
        """Create a ContractPeriod matching the MDR fixture's contract and firm."""
        self.contract_period = ContractPeriod.objects.create(
            company_id="daac1370-ee61-45ce-ad13-63aa131bf4e6",
            contract_id=self.MDR_CONTRACT,
            hours=8.0,
            working_schedules=[
                {
                    "start_time": "07:30",
                    "end_time": "12:00",
                    "days_of_week": [1, 2, 3, 4, 5],
                    "period": "morning",
                },
                {
                    "start_time": "13:00",
                    "end_time": "17:18",
                    "days_of_week": [1, 2, 3, 4, 5],
                    "period": "afternoon",
                },
            ],
        )
        self.contract_period.firms.add(self.MDR_FIRM)

    def _post(self, client, payload):
        headers = {"HTTP_USER_AGENT": "Mozilla/5.0", "REMOTE_ADDR": "127.0.0.1"}
        return client.post(
            path="/RecalculateExtraHours/",
            data={"data": {"type": "RecalculateExtraHours", "attributes": payload}},
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            **headers
        )

    def test_missing_fields_returns_400(self, client):
        response = self._post(client, {"mdr_uuid": self.MDR_UUID})
        assert response.status_code == 400

    def test_invalid_mdr_returns_404(self, client):
        response = self._post(
            client,
            {
                "mdr_uuid": "00000000-0000-0000-0000-000000000000",
                "extra_hours": [],
            },
        )
        assert response.status_code == 404

    @patch("apps.daily_reports.views.is_holiday_for_firm", return_value=False)
    def test_successful_calculation_equipment(self, mock_holiday, client):
        """
        is_worker=False (default): MDR date 2021-03-08 (Monday).
        Contract: 7:30-12:00, 13:00-17:18. Worked: 06:30-12:00, 13:00-18:18.
        Excess = 2h, returned as extra_hours (sum of all categories).
        """
        payload = {
            "mdr_uuid": self.MDR_UUID,
            "extra_hours": [
                {
                    "morningStart": "06:30",
                    "morningEnd": "12:00",
                    "afternoonStart": "13:00",
                    "afternoonEnd": "18:18",
                }
            ],
        }
        response = self._post(client, payload)
        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        data = content["data"]
        assert len(data) == 1
        assert data[0]["extraHours"] == "02:00"
        assert data[0]["absence"] == "00:00"
        assert data[0]["compensation"] == "00:00"
        assert data[0]["index"] == 0

    @patch("apps.daily_reports.views.is_holiday_for_firm", return_value=False)
    def test_successful_calculation_worker(self, mock_holiday, client):
        """
        is_worker=True: MDR date 2021-03-08 (Monday).
        Contract: 7:30-12:00, 13:00-17:18. Worked: 06:30-12:00, 13:00-18:18.
        Excess = 2h daytime -> extra_hours_50_day.
        """
        payload = {
            "mdr_uuid": self.MDR_UUID,
            "is_worker": True,
            "extra_hours": [
                {
                    "morningStart": "06:30",
                    "morningEnd": "12:00",
                    "afternoonStart": "13:00",
                    "afternoonEnd": "18:18",
                }
            ],
        }
        response = self._post(client, payload)
        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        data = content["data"]
        assert len(data) == 1
        assert data[0]["extraHours50Day"] == "02:00"
        assert data[0]["extraHours50Night"] == "00:00"
        assert data[0]["extraHours100Day"] == "00:00"
        assert data[0]["extraHours100Night"] == "00:00"
        assert data[0]["absence"] == "00:00"
        assert data[0]["compensation"] == "00:00"
        assert data[0]["index"] == 0

    @patch("apps.daily_reports.views.is_holiday_for_firm", return_value=False)
    def test_multiple_resources_equipment(self, mock_holiday, client):
        """is_worker=False: multiple resource items."""
        payload = {
            "mdr_uuid": self.MDR_UUID,
            "extra_hours": [
                {
                    "morningStart": "06:30",
                    "morningEnd": "12:00",
                    "afternoonStart": "13:00",
                    "afternoonEnd": "18:18",
                },
                {
                    "morningStart": "08:30",
                    "morningEnd": "12:00",
                    "afternoonStart": "14:00",
                    "afternoonEnd": "17:18",
                },
            ],
        }
        response = self._post(client, payload)
        assert response.status_code == status.HTTP_200_OK

        content = json.loads(response.content)
        data = content["data"]
        assert len(data) == 2
        assert data[0]["extraHours"] == "02:00"
        assert data[0]["index"] == 0
        assert data[1]["absence"] == "02:00"
        assert data[1]["index"] == 1

    @patch("apps.daily_reports.views.is_holiday_for_firm", return_value=False)
    def test_response_keys_equipment(self, mock_holiday, client):
        """is_worker=False: response should have extraHours, absence, compensation."""
        payload = {
            "mdr_uuid": self.MDR_UUID,
            "extra_hours": [{"morningStart": "07:30", "morningEnd": "12:00"}],
        }
        response = self._post(client, payload)
        content = json.loads(response.content)
        item = content["data"][0]
        assert "extraHours" in item
        assert "absence" in item
        assert "compensation" in item
        assert "extraHours50" not in item
        assert "extraHours50Day" not in item

    @patch("apps.daily_reports.views.is_holiday_for_firm", return_value=False)
    def test_response_keys_worker(self, mock_holiday, client):
        """is_worker=True: response should have the 4 day/night breakdown fields."""
        payload = {
            "mdr_uuid": self.MDR_UUID,
            "is_worker": True,
            "extra_hours": [{"morningStart": "07:30", "morningEnd": "12:00"}],
        }
        response = self._post(client, payload)
        content = json.loads(response.content)
        item = content["data"][0]
        assert "extraHours50Day" in item
        assert "extraHours50Night" in item
        assert "extraHours100Day" in item
        assert "extraHours100Night" in item
        assert "absence" in item
        assert "compensation" in item
        assert "extraHours50" not in item
        assert "extraHours" not in item
