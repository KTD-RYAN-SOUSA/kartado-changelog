from datetime import datetime
from unittest.mock import patch

import pytest
import pytz
from dateutil.relativedelta import relativedelta
from django.utils.timezone import now

from apps.companies.create_instances_company_model import (
    create_instances_company_model,
    is_user_active,
)
from apps.companies.models import (
    Company,
    CompanyUsage,
    SingleCompanyUsage,
    User,
    UserInCompany,
    UserUsage,
)

pytestmark = pytest.mark.django_db


class TestCreateInstancesCompanyModel:
    @pytest.fixture
    def setup_data(self):
        """Setup basic test data"""
        self.company = Company.objects.create(
            name="Test Company", cnpj="12345678901234", active=True
        )
        self.active_user = User.objects.create(
            email="test@example.com", username="active_user"
        )
        user_in_company = UserInCompany(
            user=self.active_user, company=self.company, is_active=True
        )
        user_in_company.save()
        self.inactive_user = User.objects.create(
            email="inactive@example.com", username="inactive_user"
        )
        user_in_company = UserInCompany(
            user=self.inactive_user, company=self.company, is_active=False
        )
        user_in_company.save()

        utc = pytz.UTC
        self.current_date = now().date()
        self.current_month = self.current_date.month
        self.current_year = self.current_date.year
        last_month = (self.current_date - relativedelta(months=1)).month
        start_year = (
            self.current_year if self.current_month != 1 else self.current_year - 1
        )
        self.start_date = datetime(start_year, last_month, 1, 3, 0).replace(tzinfo=utc)
        self.end_date = datetime(
            self.current_year, self.current_month, 1, 3, 0
        ).replace(tzinfo=utc)

    def test_create_instances_company_model_basic(self, setup_data):
        """Test basic creation of CompanyUsage and UserUsage"""

        def mock_get_user_status(uic_list, start_date, end_date):
            return [self.active_user], [self.inactive_user]

        with patch(
            "apps.companies.create_instances_company_model.get_user_status",
            side_effect=mock_get_user_status,
        ):
            create_instances_company_model()

        company_usage = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=self.company.cnpj
        ).first()

        assert company_usage is not None
        assert self.company.name in company_usage.company_names
        assert company_usage.companies.filter(uuid=self.company.uuid).exists()
        assert company_usage.user_count == 1

        user_usage = UserUsage.objects.filter(
            user=self.active_user, company_usage=company_usage
        ).first()

        assert user_usage is not None
        assert user_usage.is_counted is True

    def test_is_user_active(self, setup_data):
        """Test is_user_active function"""

        user_in_company = self.active_user.companies_membership.get(
            company=self.company
        )
        assert is_user_active(user_in_company, self.start_date, self.end_date) is True
        user_in_company.is_active = False
        user_in_company.save()

        # It stays true because it was true at some point
        assert is_user_active(user_in_company, self.start_date, self.end_date) is True

        inactive_uic = self.inactive_user.companies_membership.get(company=self.company)

        assert is_user_active(inactive_uic, self.start_date, self.end_date) is False

    def test_active_and_inactive_users(self, setup_data):
        """Test handling of active and inactive users"""

        def mock_get_user_status(uic_list, start_date, end_date):
            return [self.active_user], [self.inactive_user]

        with patch(
            "apps.companies.create_instances_company_model.get_user_status",
            side_effect=mock_get_user_status,
        ):
            create_instances_company_model()

        company_usage = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=self.company.cnpj
        ).first()

        assert company_usage.user_count == 1

        active_user_usage = UserUsage.objects.get(
            user=self.active_user, company_usage=company_usage
        )
        assert active_user_usage.is_counted is True

        inactive_user_usage = UserUsage.objects.get(
            user=self.inactive_user, company_usage=company_usage
        )
        assert inactive_user_usage.is_counted is False

    def test_invalid_cnpj_excluded(self, setup_data):
        """Test that companies with invalid CNPJ are excluded"""
        create_instances_company_model()

        company_usage1 = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj="00000000000000"
        ).first()

        company_usage2 = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj="00.000.000/0000-00"
        ).first()

        assert company_usage1 is None
        assert company_usage2 is None

    def test_inactive_company_excluded(self, setup_data):
        """Test that inactive companies are excluded"""
        inactive_company = Company.objects.create(
            name="Inactive Company", cnpj="98765432101234", active=False
        )

        create_instances_company_model()

        company_usage = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=inactive_company.cnpj
        ).first()

        assert company_usage is None

    def test_alphanumeric_cnpj_grouping(self, setup_data):
        """KAP-46: a agregação mensal do "Meu Plano" deve gerar um
        `CompanyUsage` distinto para cada CNPJ alfanumérico, sem colapsar
        com CNPJs numéricos legados de outras Companies (RN09)."""
        # Cria 2 companies alfanuméricas distintas + a numérica do setup_data
        alpha_company_1 = Company.objects.create(
            name="Alpha Company 1", cnpj="12.ABC.345/01DE-35", active=True
        )
        alpha_company_2 = Company.objects.create(
            name="Alpha Company 2", cnpj="AB.CDE.FGH/0001-95", active=True
        )

        create_instances_company_model()

        # Cada CNPJ vira um CompanyUsage próprio
        usage_legacy = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=self.company.cnpj
        ).first()
        usage_alpha_1 = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=alpha_company_1.cnpj
        ).first()
        usage_alpha_2 = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=alpha_company_2.cnpj
        ).first()

        assert usage_legacy is not None
        assert usage_alpha_1 is not None
        assert usage_alpha_2 is not None

        # Não houve colapso entre os agrupamentos
        assert usage_legacy.uuid != usage_alpha_1.uuid
        assert usage_alpha_1.uuid != usage_alpha_2.uuid
        assert usage_legacy.uuid != usage_alpha_2.uuid

        # Cada agrupamento contém exatamente a sua company
        assert usage_alpha_1.companies.filter(uuid=alpha_company_1.uuid).exists()
        assert usage_alpha_2.companies.filter(uuid=alpha_company_2.uuid).exists()

    def test_amp_email_excluded(self, setup_data):
        """Test that users with AMP domain emails are excluded from UserUsage"""
        amp_user = User.objects.create(email="user@client.amp.br", username="amp_user")
        uic = UserInCompany(user=amp_user, company=self.company, is_active=True)
        uic.save()

        create_instances_company_model()

        company_usage = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=self.company.cnpj
        ).first()

        assert not UserUsage.objects.filter(
            user=amp_user, company_usage=company_usage
        ).exists()

    def test_ajr_email_excluded(self, setup_data):
        """Test that users with AJR domain emails are excluded from UserUsage"""
        ajr_user = User.objects.create(email="user@client.ajr.br", username="ajr_user")
        uic = UserInCompany(user=ajr_user, company=self.company, is_active=True)
        uic.save()

        create_instances_company_model()

        company_usage = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=self.company.cnpj
        ).first()

        assert not UserUsage.objects.filter(
            user=ajr_user, company_usage=company_usage
        ).exists()

    def test_amp_in_name_not_excluded(self, setup_data):
        """Test that users with 'amp' in their name (but not domain) are counted normally"""

        def mock_get_user_status(uic_list, start_date, end_date):
            return [self.campos_user], []

        self.campos_user = User.objects.create(
            email="campos@empresa.com", username="campos_user"
        )
        uic = UserInCompany(user=self.campos_user, company=self.company, is_active=True)
        uic.save()

        with patch(
            "apps.companies.create_instances_company_model.get_user_status",
            side_effect=mock_get_user_status,
        ):
            create_instances_company_model()

        company_usage = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=self.company.cnpj
        ).first()

        assert UserUsage.objects.filter(
            user=self.campos_user, company_usage=company_usage
        ).exists()

    def test_single_company_usage_created_after_cron(self, setup_data):
        """Test that SingleCompanyUsage is created for the company after running the cron"""

        def mock_get_user_status(uic_list, start_date, end_date):
            return [self.active_user], [self.inactive_user]

        with patch(
            "apps.companies.create_instances_company_model.get_user_status",
            side_effect=mock_get_user_status,
        ):
            create_instances_company_model()

        company_usage = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=self.company.cnpj
        ).first()

        assert SingleCompanyUsage.objects.filter(
            company_usage=company_usage, company=self.company
        ).exists()

    def test_companies_field_populated_in_user_usage(self, setup_data):
        """Test that UserUsage.companies is populated after running the cron"""

        def mock_get_user_status(uic_list, start_date, end_date):
            return [self.active_user], [self.inactive_user]

        with patch(
            "apps.companies.create_instances_company_model.get_user_status",
            side_effect=mock_get_user_status,
        ):
            create_instances_company_model()

        company_usage = CompanyUsage.objects.filter(
            date=self.end_date.date(), cnpj=self.company.cnpj
        ).first()

        user_usage = UserUsage.objects.filter(
            user=self.active_user, company_usage=company_usage
        ).first()

        assert user_usage is not None
        assert len(user_usage.companies) > 0

    def test_current_month_snapshot_created(self, setup_data):
        """Test that a CompanyUsage with date = next_end_date.date() is created."""
        next_end_date = self.end_date + relativedelta(months=1)

        create_instances_company_model()

        company_usage = CompanyUsage.objects.filter(
            date=next_end_date.date(), cnpj=self.company.cnpj
        ).first()

        assert company_usage is not None
