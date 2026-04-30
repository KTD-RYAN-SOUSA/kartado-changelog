import json
from datetime import datetime, timedelta

import pytest
from rest_framework import status

from apps.occurrence_records.models import OccurrenceType
from apps.services.models import Goal, GoalAggregate, Service
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestGoalAggregate(TestBase):
    model = "GoalAggregate"

    def test_list_goal_aggregate(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_goal_aggregate_without_queryset(self, client):

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

    def test_list_goal_aggregate_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_goal_aggregate(self, client):

        aggregate = GoalAggregate.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(aggregate.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_goal_aggregate_without_company(self, client):

        aggregate = GoalAggregate.objects.filter(company=self.company).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(aggregate.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_goal_aggregate(self, client):

        occtype = OccurrenceType.objects.filter(company=self.company).first()
        service = Service.objects.filter(
            company=self.company, occurrence_types=occtype
        ).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "startDate": "2019-04-01T00:00:00-03:00",
                        "endDate": "2019-04-30T00:00:00-03:00",
                    },
                    "relationships": {
                        "company": {
                            "data": {
                                "type": "Company",
                                "id": str(self.company.pk),
                            }
                        },
                        "add_goals": {
                            "data": [
                                {
                                    "occurrence_type": str(occtype.pk),
                                    "service": str(service.pk),
                                    "amount": 5,
                                }
                            ]
                        },
                    },
                }
            },
        )

        # __str__ method
        content = json.loads(response.content)
        obj_created = GoalAggregate.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

        # object created
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_goal_aggregate_without_company_id(self, client):

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {
                        "startDate": "2019-04-01T00:00:00-03:00",
                        "endDate": "2019-04-30T00:00:00-03:00",
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_goal_aggregate(self, client):

        aggregate = GoalAggregate.objects.filter(company=self.company)[0]
        types = Goal.objects.all().values_list("occurrence_type_id", flat=True)
        occtype = OccurrenceType.objects.filter(
            company=self.company, occurrences_service__isnull=False
        ).exclude(pk__in=types)[0]
        service = Service.objects.filter(
            company=self.company, occurrence_types=occtype
        )[0]

        response = client.patch(
            path="/{}/{}/".format(self.model, str(aggregate.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(aggregate.pk),
                    "attributes": {"startDate": "2019-04-10T00:00:00-03:00"},
                    "relationships": {
                        "add_goals": {
                            "data": [
                                {
                                    "occurrence_type": str(occtype.pk),
                                    "service": str(service.pk),
                                    "amount": 5,
                                }
                            ]
                        }
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_update_goal_aggregate_with_wrong_occtype(self, client):

        aggregate = GoalAggregate.objects.filter(company=self.company).first()
        goal = aggregate.goals.first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(aggregate.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(aggregate.pk),
                    "attributes": {"startDate": "2019-04-10T00:00:00-03:00"},
                    "relationships": {
                        "add_goals": {
                            "data": [
                                {
                                    "occurrence_type": str(goal.occurrence_type.pk),
                                    "service": str(goal.service.pk),
                                    "amount": 5,
                                }
                            ]
                        }
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_goal_aggregate_with_date_conflict(self, client):

        aggregate = GoalAggregate.objects.filter(company=self.company).first()
        another_aggregate = GoalAggregate.objects.create(
            number="test",
            start_date=datetime.now().replace(microsecond=0).isoformat(),
            end_date=(
                datetime.now().replace(microsecond=0) + timedelta(days=1)
            ).isoformat(),
            company=self.company,
        )

        response = client.patch(
            path="/{}/{}/".format(self.model, str(aggregate.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(aggregate.pk),
                    "attributes": {
                        "startDate": another_aggregate.start_date,
                        "endDate": another_aggregate.end_date,
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_goal_aggregate_with_wrong_date(self, client):

        aggregate = GoalAggregate.objects.filter(company=self.company).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(aggregate.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(aggregate.pk),
                    "attributes": {
                        "startDate": "2019-04-10T00:00:00-03:00",
                        "endDate": "2019-04-09T00:00:00-03:00",
                    },
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_goal_aggregate(self, client):

        aggregate = GoalAggregate.objects.filter(company=self.company).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(aggregate.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT
