import json
from datetime import date, datetime

import pytest
import pytz
from dateutil.relativedelta import relativedelta
from rest_framework import status

from apps.companies.models import (
    Company,
    CompanyUsage,
    SingleCompanyUsage,
    UserInCompany,
    UserUsage,
)
from apps.users.models import User
from helpers.testing.tests import BaseModelTests

pytestmark = pytest.mark.django_db


class TestSingleCompanyUsage(BaseModelTests):
    def init_manual_fields(self):
        self.model_class = SingleCompanyUsage
        self.model_attributes = {
            "user_count": 3,
        }
        self.update_attributes = {
            "user_count": 5,
        }

        # Separate company_usage for listing (has pre-created instance)
        list_company_usage = CompanyUsage.objects.create(
            date="2022-04-01", plan_name="List Test plan"
        )
        list_company_usage.companies.add(self.company)
        SingleCompanyUsage.objects.create(
            company_usage=list_company_usage,
            company=self.company,
            user_count=1,
        )
        self._list_company_usage = list_company_usage

        # Separate company_usage for create/patch/delete (no pre-created instance)
        create_company_usage = CompanyUsage.objects.create(
            date="2022-05-01", plan_name="Create Test plan"
        )
        create_company_usage.companies.add(self.company)

        self.model_relationships = {
            "company_usage": create_company_usage,
            "company": self.company,
        }
        # API usa permissões de CompanyUsage, não do modelo SingleCompanyUsage
        self.permission_model_name = "CompanyUsage"

    def test_model_lists_fixtures(self, client):
        path = f"/{self.model_name}/?company_usage={self._list_company_usage.pk}"
        response = client.get(**self.get_req_args(path))
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] > 0


class TestSingleCompanyUsageSignals:
    @pytest.fixture(autouse=True)
    def setup_data(self, db):
        self.company = Company.objects.create(
            name="Signal Test Company", cnpj="12345678901234", active=True
        )
        self.user = User.objects.create(
            email="valid@example.com", username="signal_test_user"
        )
        today = date.today()
        utc = pytz.UTC
        end_date = datetime(today.year, today.month, 1, 3, 0).replace(tzinfo=utc)
        next_end_date = end_date + relativedelta(months=1)
        self.first_day = next_end_date.date()

    def test_new_active_uic_creates_user_usage(self):
        uic = UserInCompany(user=self.user, company=self.company, is_active=True)
        uic.save()

        assert UserUsage.objects.filter(user=self.user).exists()
        user_usage = UserUsage.objects.get(user=self.user)
        assert user_usage.is_counted is True

    def test_new_inactive_uic_does_not_create_user_usage(self):
        uic = UserInCompany(user=self.user, company=self.company, is_active=False)
        uic.save()

        user_usage = UserUsage.objects.filter(user=self.user).first()
        assert user_usage is not None
        assert user_usage.is_counted is False

    def test_new_active_uic_creates_single_company_usage(self):
        uic = UserInCompany(user=self.user, company=self.company, is_active=True)
        uic.save()

        company_usage = CompanyUsage.objects.filter(
            date=self.first_day, cnpj=self.company.cnpj
        ).first()
        assert company_usage is not None
        assert SingleCompanyUsage.objects.filter(
            company_usage=company_usage, company=self.company
        ).exists()

    def test_new_active_uic_increments_company_usage_user_count(self):
        uic = UserInCompany(user=self.user, company=self.company, is_active=True)
        uic.save()

        company_usage = CompanyUsage.objects.get(
            date=self.first_day, cnpj=self.company.cnpj
        )
        assert company_usage.user_count == 1

    def test_new_active_uic_with_amp_email_ignored(self):
        amp_user = User.objects.create(email="user@client.amp.br", username="amp_user")
        uic = UserInCompany(user=amp_user, company=self.company, is_active=True)
        uic.save()

        assert not UserUsage.objects.filter(user=amp_user).exists()

    def test_new_active_uic_with_ajr_email_ignored(self):
        ajr_user = User.objects.create(email="user@client.ajr.br", username="ajr_user")
        uic = UserInCompany(user=ajr_user, company=self.company, is_active=True)
        uic.save()

        assert not UserUsage.objects.filter(user=ajr_user).exists()

    def test_new_active_uic_with_amp_in_name_not_ignored(self):
        campos_user = User.objects.create(
            email="campos@empresa.com", username="campos_user"
        )
        uic = UserInCompany(user=campos_user, company=self.company, is_active=True)
        uic.save()

        assert UserUsage.objects.filter(user=campos_user).exists()

    def test_reactivation_creates_user_usage(self):
        uic = UserInCompany(user=self.user, company=self.company, is_active=False)
        uic.save()

        user_usage = UserUsage.objects.filter(user=self.user).first()
        assert user_usage is not None
        assert user_usage.is_counted is False

        uic.is_active = True
        uic.save()

        user_usage.refresh_from_db()
        assert user_usage.is_counted is True

    def test_deactivation_does_not_trigger_signal(self):
        uic = UserInCompany(user=self.user, company=self.company, is_active=True)
        uic.save()

        user_usage = UserUsage.objects.get(user=self.user)
        assert user_usage.is_counted is True

        uic.is_active = False
        uic.save()

        user_usage.refresh_from_db()
        assert user_usage.is_counted is True

    def test_reactivation_uses_existing_company_usage(self):
        existing_usage = CompanyUsage.objects.create(
            date=self.first_day,
            cnpj=self.company.cnpj,
            plan_name="Existing Plan",
        )
        existing_usage.companies.add(self.company)

        uic = UserInCompany(user=self.user, company=self.company, is_active=False)
        uic.save()

        uic.is_active = True
        uic.save()

        count = CompanyUsage.objects.filter(
            date=self.first_day, cnpj=self.company.cnpj
        ).count()
        assert count == 1

        user_usage = UserUsage.objects.get(user=self.user)
        assert user_usage.company_usage == existing_usage
