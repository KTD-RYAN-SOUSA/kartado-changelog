from datetime import datetime, timedelta

import pytest
from django.db.models import Q
from rest_framework import status

from apps.companies.models import Firm
from apps.permissions.models import UserPermission
from apps.users.const.time_intervals import NOTIFICATION_INTERVALS
from apps.users.models import User, UserNotification
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestUserFilter(TestBase):
    model = "User"

    def test_filter__users_from_responsibles_hirer(self, client):
        company_id = str(self.company.pk)

        # TODO: try referente a modificação na staging onde company de subcompany
        # passa ser many to many remover remove exception assim que for implementando
        try:
            qs_users = User.objects.filter(
                Q(hirer_contracts__firm__company__pk=company_id)
                | Q(hirer_contracts__subcompany__companies__pk=company_id)
            ).distinct()
        except Exception:
            qs_users = User.objects.filter(
                Q(hirer_contracts__firm__company__pk=company_id)
                | Q(hirer_contracts__subcompany__company__pk=company_id)
            ).distinct()

        response = client.get(
            path="/{}/?company={}&page_size=10000&responsibles_hirer={}".format(
                self.model, company_id, company_id
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] > 0
        assert response.data["meta"]["pagination"]["count"] == qs_users.count()

    def test_filter__users_from_responsibles_hired(self, client):
        company_id = str(self.company.pk)

        # TODO: try referente a modificação na staging onde company de subcompany
        # passa ser many to many remover remove exception assim que for implementando
        try:
            qs_users = User.objects.filter(
                Q(hired_contracts__firm__company__pk=company_id)
                | Q(hired_contracts__subcompany__companies__pk=company_id)
            ).distinct()
        except Exception:
            qs_users = User.objects.filter(
                Q(hired_contracts__firm__company__pk=company_id)
                | Q(hired_contracts__subcompany__company__pk=company_id)
            ).distinct()

        response = client.get(
            path="/{}/?company={}&page_size=10000&responsibles_hired={}".format(
                self.model, company_id, company_id
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] > 0
        assert response.data["meta"]["pagination"]["count"] == qs_users.count()

    def test_filter_by_uuid(self, client):
        """Test filtering by UUID."""
        user = self.company.users.all().exclude(pk=self.user.pk)[0]

        response = client.get(
            path="/{}/?company={}&uuid={}".format(
                self.model, str(self.company.pk), str(user.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        data_key = "data" if "data" in response.data else "results"
        assert response.data["meta"]["pagination"]["count"] == 1

        uuid_field = "uuid" if "uuid" in response.data[data_key][0] else "pk"
        assert response.data[data_key][0][uuid_field] == str(user.pk)

    def test_filter_by_only_company(self, client):
        """Test filtering by specific company."""
        response = client.get(
            path="/{}/?company={}&only_company={}".format(
                self.model, str(self.company.pk), str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        users_count = User.objects.filter(companies=self.company).count()
        assert response.data["meta"]["pagination"]["count"] == users_count

    def test_filter_by_firm(self, client):
        """Test filtering by firm."""
        firm = Firm.objects.filter(company=self.company).first()

        if firm:
            response = client.get(
                path="/{}/?company={}&firm={}".format(
                    self.model, str(self.company.pk), str(firm.pk)
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
            )

            assert response.status_code == status.HTTP_200_OK

            users_count = User.objects.filter(user_firms=firm).count()
            assert response.data["meta"]["pagination"]["count"] == users_count

    def test_filter_is_active(self, client):
        """Test filtering by active status."""
        response = client.get(
            path="/{}/?company={}&is_active=true".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] > 0

    def test_filter_has_expiration_date(self, client):
        """Test filtering by expiration date."""
        user = self.company.users.all().exclude(pk=self.user.pk)[0]
        membership = user.companies_membership.filter(company=self.company).first()

        if membership:
            membership.expiration_date = datetime.now() + timedelta(days=30)
            membership.save()

        response = client.get(
            path="/{}/?company={}&has_expiration_date=true".format(
                self.model, str(self.company.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK

        users_with_expiration = (
            User.objects.filter(companies_membership__expiration_date__isnull=False)
            .distinct()
            .count()
        )

        assert response.data["meta"]["pagination"]["count"] == users_with_expiration

    def test_filter_by_permission(self, client):
        """Test permission filtering."""
        permission = UserPermission.objects.filter(companies=self.company).first()

        if permission:
            response = client.get(
                path="/{}/?company={}&permission={}".format(
                    self.model, str(self.company.pk), str(permission.pk)
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
            )

            assert response.status_code == status.HTTP_200_OK

            users_with_permission = (
                User.objects.filter(
                    companies_membership__company=self.company,
                    companies_membership__permissions=permission,
                )
                .distinct()
                .count()
            )

            assert response.data["meta"]["pagination"]["count"] == users_with_permission

    def test_filter_only_internal(self, client):
        """Test filtering of internal users only."""
        internal_firm = Firm.objects.filter(
            company=self.company, is_company_team=True
        ).first()

        if internal_firm:
            response = client.get(
                path="/{}/?company={}&only_internal=true".format(
                    self.model, str(self.company.pk)
                ),
                content_type="application/vnd.api+json",
                HTTP_AUTHORIZATION="JWT {}".format(self.token),
            )

            assert response.status_code == status.HTTP_200_OK
            assert response.data["meta"]["pagination"]["count"] > 0

    def test_filter_user_notification_by_user(self, client):
        """Test filtering notifications by user."""
        daily_interval = None
        for choice in NOTIFICATION_INTERVALS:
            if choice[1] == "daily":
                daily_interval = choice[0]
                break

        if daily_interval is None:
            daily_interval = timedelta(days=1)

        notification = UserNotification.objects.create(
            user=self.user,
            notification="test_notification",
            notification_type="email",
            time_interval=daily_interval,
        )
        notification.companies.add(self.company)

        response = client.get(
            path="/{}/?company={}&user={}".format(
                self.model, str(self.company.pk), str(self.user.pk)
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["meta"]["pagination"]["count"] >= 1
