import json

import pytest
from rest_framework import status

from apps.occurrence_records.models import OccurrenceType
from apps.services.models import Goal, GoalAggregate, Service
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db


class TestGoal(TestBase):
    model = "Goal"

    def test_list_goal(self, client):

        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_filter_goal(self, client):

        date = "01/01/2019"

        response = client.get(
            path="/{}/?company={}&date={}&page_size=1".format(
                self.model, str(self.company.pk), date
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_goal_without_queryset(self, client):

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

    def test_list_goal_without_company(self, client):

        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_goal(self, client):

        goal = Goal.objects.filter(aggregate__company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model, str(goal.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_goal_without_company(self, client):

        goal = Goal.objects.filter(aggregate__company=self.company).first()

        response = client.get(
            path="/{}/{}/".format(self.model, str(goal.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_goal_without_company_uuid(self, client):

        goal = Goal.objects.filter(aggregate__company=self.company).first()

        response = client.get(
            path="/{}/{}/?company={}".format(self.model, str(goal.pk), "not_uuid"),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_goal(self, client):

        aggregate = GoalAggregate.objects.filter(company=self.company)[0]
        except_types = list(
            set(Goal.objects.all().values_list("occurrence_type_id", flat=True))
        )
        occtype = OccurrenceType.objects.filter(
            company=self.company, occurrences_service__isnull=False
        ).exclude(pk__in=except_types)[0]
        service = Service.objects.filter(
            company=self.company, occurrence_types=occtype
        )[0]

        response = client.post(
            path="/{}/?company={}".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"amount": 5},
                    "relationships": {
                        "aggregate": {
                            "data": {
                                "type": "GoalAggregate",
                                "id": str(aggregate.pk),
                            }
                        },
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occtype.pk),
                            }
                        },
                        "service": {"data": {"type": "Service", "id": str(service.pk)}},
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # __str__ method
        content = json.loads(response.content)
        obj_created = Goal.objects.get(pk=content["data"]["id"])
        assert obj_created.__str__()

    def test_create_goal_bulk_create(self, client):

        goal = Goal.objects.filter(aggregate__company=self.company).first()
        occtype = (
            OccurrenceType.objects.filter(company=self.company)
            .exclude(pk=goal.occurrence_type.pk)
            .first()
        )
        service = (
            Service.objects.filter(company=self.company)
            .exclude(pk=goal.service.pk)
            .first()
        )

        response = client.post(
            path="/{}/bulk_create/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "aggregate": {
                            "data": {
                                "type": "GoalAggregate",
                                "id": str(goal.aggregate.pk),
                            }
                        },
                        "goals": {
                            "data": [
                                {
                                    "occurrence_type": str(occtype.pk),
                                    "amount": 5,
                                    "service": str(service.pk),
                                }
                            ]
                        },
                    },
                }
            },
        )

        # object created
        assert response.status_code == status.HTTP_201_CREATED

        # Test permission

        response = client.post(
            path="/{}/bulk_create/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "goals": {
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

        # object created
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Test goal with same period

        goal = Goal.objects.filter(aggregate__company=self.company).first()

        response = client.post(
            path="/{}/bulk_create/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {},
                    "relationships": {
                        "aggregate": {
                            "data": {
                                "type": "GoalAggregate",
                                "id": str(goal.aggregate.pk),
                            }
                        },
                        "goals": {
                            "data": [
                                {
                                    "occurrence_type": str(goal.occurrence_type.pk),
                                    "service": str(goal.service.pk),
                                    "amount": 5,
                                }
                            ]
                        },
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_goal_without_aggregate_id(self, client):

        occtype = OccurrenceType.objects.filter(company=self.company).first()

        response = client.post(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "attributes": {"amount": 5},
                    "relationships": {
                        "occurrenceType": {
                            "data": {
                                "type": "OccurrenceType",
                                "id": str(occtype.pk),
                            }
                        }
                    },
                }
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_goal(self, client):

        goal = Goal.objects.filter(aggregate__company=self.company).first()

        response = client.patch(
            path="/{}/{}/".format(self.model, str(goal.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={
                "data": {
                    "type": self.model,
                    "id": str(goal.pk),
                    "attributes": {"amount": 10},
                }
            },
        )

        # object changed
        assert response.status_code == status.HTTP_200_OK

    def test_delete_goal(self, client):

        goal = Goal.objects.filter(aggregate__company=self.company).first()

        response = client.delete(
            path="/{}/{}/".format(self.model, str(goal.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        # object changed
        assert response.status_code == status.HTTP_204_NO_CONTENT
