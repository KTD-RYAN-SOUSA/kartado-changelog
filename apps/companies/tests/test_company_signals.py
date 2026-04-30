from unittest.mock import patch

import pytest

from apps.companies.models import Company
from apps.reportings.models import RecordMenu

pytestmark = pytest.mark.django_db


def test_create_active_company_menus_signal():
    """Test that create_active_company_menus signal creates menus when company becomes active"""
    # Mock both signals to avoid automatic menu creation
    with patch("apps.companies.signals.create_company_menus") as mock_create_menus:
        with patch("apps.reportings.helpers.default_menus.create_company_menus"):
            company = Company.objects.create(
                name="Test Company", active=False, cnpj="12.345.678/0001-90"
            )

            RecordMenu.objects.filter(company=company).delete()

            mock_create_menus.reset_mock()

            assert not RecordMenu.objects.filter(
                company=company, system_default=True
            ).exists()

            company.active = True
            company.save()

            mock_create_menus.assert_called_once_with(company)


def test_create_active_company_menus_signal_with_existing_menu():
    with patch("apps.companies.signals.create_company_menus") as mock_create_menus:
        with patch("apps.reportings.helpers.default_menus.create_company_menus"):
            company = Company.objects.create(
                name="Test Company", active=False, cnpj="12.345.678/0001-91"
            )

            RecordMenu.objects.filter(company=company).delete()

            RecordMenu.objects.create(
                company=company, system_default=True, name="Default", order=1
            )

            mock_create_menus.reset_mock()

            company.active = True
            company.save()

            mock_create_menus.assert_not_called()


def test_create_active_company_menus_signal_no_trigger_when_already_active():
    with patch("apps.companies.signals.create_company_menus") as mock_create_menus:
        with patch("apps.reportings.helpers.default_menus.create_company_menus"):
            company = Company.objects.create(
                name="Test Company", active=True, cnpj="12.345.678/0001-92"
            )

            mock_create_menus.reset_mock()

            company.name = "Updated Name"
            company.save()

            mock_create_menus.assert_not_called()


def test_create_active_company_menus_signal_only_triggers_false_to_true():
    with patch("apps.companies.signals.create_company_menus") as mock_create_menus:
        with patch("apps.reportings.helpers.default_menus.create_company_menus"):
            company = Company.objects.create(
                name="Test Company", active=True, cnpj="12.345.678/0001-93"
            )

            mock_create_menus.reset_mock()

            company.active = False
            company.save()

            company.active = True
            company.save()

            mock_create_menus.assert_called_once_with(company)
