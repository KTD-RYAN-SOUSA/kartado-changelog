import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from apps.companies.filters import CompanyFilter
from apps.companies.models import Company, UserInCompany

User = get_user_model()


@pytest.mark.django_db
def test_company_filter_get_active_true():
    factory = APIRequestFactory()

    # 1. Cria usuário e empresas
    user = User.objects.create(username="tester")
    company_active = Company.objects.create(name="Empresa Ativa")
    company_inactive = Company.objects.create(name="Empresa Inativa")

    # 2. Relaciona usuário com empresas
    UserInCompany.objects.create(user=user, company=company_active, is_active=True)
    UserInCompany.objects.create(user=user, company=company_inactive, is_active=False)

    # 3. Simula request com ?active=true
    request = factory.get("/companies", {"active": True})
    request.user = user

    # 4. Aplica filtro
    qs = CompanyFilter(
        data=request.GET, queryset=Company.objects.all(), request=request
    ).qs

    # 5. Verifica resultado
    assert company_active in qs
    assert company_inactive not in qs


@pytest.mark.django_db
def test_company_filter_get_active_false():
    factory = APIRequestFactory()

    user = User.objects.create(username="tester2")
    company_active = Company.objects.create(name="Empresa Ativa")
    company_inactive = Company.objects.create(name="Empresa Inativa")

    UserInCompany.objects.create(user=user, company=company_active, is_active=True)
    UserInCompany.objects.create(user=user, company=company_inactive, is_active=False)

    request = factory.get("/companies", {"active": False})
    request.user = user

    qs = CompanyFilter(
        data=request.GET, queryset=Company.objects.all(), request=request
    ).qs

    assert company_inactive in qs
    assert company_active not in qs
