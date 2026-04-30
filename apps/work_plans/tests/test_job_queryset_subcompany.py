import json
from unittest.mock import Mock

import pytest
from rest_framework import status

from apps.companies.models import Firm
from apps.users.models import User
from apps.work_plans.models import Job
from helpers.testing.fixtures import TestBase, false_permission

pytestmark = pytest.mark.django_db

# UUIDs definidos nos arquivos de fixture 200-204
SUBCOMPANY_A = "aaa00001-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SUBCOMPANY_B = "aaa00002-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
FIRM_A1 = "bbb00001-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
FIRM_A2 = "bbb00002-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
FIRM_B1 = "bbb00003-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
JOB_A1 = "eee00001-eeee-eeee-eeee-eeeeeeeeeeee"
JOB_A2 = "eee00002-eeee-eeee-eeee-eeeeeeeeeeee"
JOB_B1 = "eee00003-eeee-eeee-eeee-eeeeeeeeeeee"

ENGIE2_UUID = "e7cfb4c3-ddd1-43e2-8439-c4c6f0a98383"
ENGIE3_UUID = "4e29d1e0-9745-48d3-b38f-b1210e683e00"


def _queryset_for_user(user, company_uuid, queryset_values):
    """Simula get_queryset do JobViewSet com permissões mockadas."""
    from apps.work_plans.views import JobViewSet

    view = JobViewSet()
    view.action = "list"

    request = Mock()
    request.user = user
    request.query_params = {"company": str(company_uuid)}

    permissions = Mock()
    permissions.get_allowed_queryset.return_value = queryset_values

    view.request = request
    view.permissions = permissions
    view.get_serializer_class = Mock(
        return_value=Mock(setup_eager_loading=lambda qs: qs)
    )
    return view.get_queryset()


@pytest.mark.usefixtures("subcompany_subtest_data")
class TestJobQuerysetSubcompany(TestBase):
    """
    Testes do queryset "subcompany" para Jobs.

    Dados de fixture (arquivos 200-204):
      - SubCompany A (aaa00001): Firm_A1 (bbb00001) e Firm_A2 (bbb00002)
      - SubCompany B (aaa00002): Firm_B1 (bbb00003)
      - HOMOLOGATOR (0aa50773) -> manager -> Firm_A1
      - engie2 (e7cfb4c3) -> UserInFirm -> Firm_B1
      - Jobs: SUB-JOB-001 (Firm_A1), SUB-JOB-002 (Firm_A2), SUB-JOB-003 (Firm_B1)
    """

    model = "Job"

    def _api_uuids(self, client, token):
        """Consulta a API e retorna os UUIDs dos jobs retornados."""
        response = client.get(
            path=f"/{self.model}/?company={self.company.pk}&page_size=100",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )
        assert response.status_code == status.HTTP_200_OK
        content = json.loads(response.content)
        return [item["id"] for item in content["data"]]

    def test_sees_all_firms_of_own_subcompany(self, client):
        """HOMOLOGATOR em Firm_A1 ve jobs de Firm_A1 e Firm_A2 (mesma SubCompany_A)."""
        false_permission(self.user, self.company, self.model, allowed="subcompany")
        uuids = self._api_uuids(client, self.token)
        assert JOB_A1 in uuids
        assert JOB_A2 in uuids

    def test_does_not_see_other_subcompany(self, client):
        """HOMOLOGATOR em SubCompany_A nao ve jobs de SubCompany_B."""
        false_permission(self.user, self.company, self.model, allowed="subcompany")
        uuids = self._api_uuids(client, self.token)
        assert JOB_B1 not in uuids

    def test_firms_without_subcompany_excluded(self, client):
        """Jobs de equipes sem SubCompany nao aparecem no queryset subcompany."""
        false_permission(self.user, self.company, self.model, allowed="subcompany")
        uuids = set(self._api_uuids(client, self.token))
        existing = (
            Job.objects.filter(company=self.company)
            .exclude(uuid__in=[JOB_A1, JOB_A2, JOB_B1])
            .values_list("uuid", flat=True)
        )
        for uuid in existing:
            assert str(uuid) not in uuids

    def test_user_b_sees_only_subcompany_b(self):
        """engie2 em Firm_B1 (SubCompany_B) ve apenas jobs de SubCompany_B."""
        engie2 = User.objects.get(uuid=ENGIE2_UUID)
        qs = _queryset_for_user(engie2, self.company.pk, ["subcompany"])
        uuids = set(str(j.uuid) for j in qs)
        assert JOB_B1 in uuids
        assert JOB_A1 not in uuids
        assert JOB_A2 not in uuids

    def test_user_without_subcompany_sees_nothing(self):
        """Usuario cujas equipes nao tem SubCompany nao ve nenhum job."""
        engie3 = User.objects.get(uuid=ENGIE3_UUID)
        qs = _queryset_for_user(engie3, self.company.pk, ["subcompany"])
        uuids = set(str(j.uuid) for j in qs)
        assert JOB_A1 not in uuids
        assert JOB_A2 not in uuids
        assert JOB_B1 not in uuids

    def test_user_in_two_subcompanies_sees_both(self):
        """Usuario em equipes de 2 SubCompanies diferentes ve jobs de ambas."""
        engie2 = User.objects.get(uuid=ENGIE2_UUID)
        firm_a1 = Firm.objects.get(uuid=FIRM_A1)
        firm_a1.users.add(engie2)

        qs = _queryset_for_user(engie2, self.company.pk, ["subcompany"])
        uuids = set(str(j.uuid) for j in qs)
        assert JOB_A1 in uuids
        assert JOB_A2 in uuids
        assert JOB_B1 in uuids

    def test_other_users_not_affected(self, client):
        """Adicionar engie2 a Firm_A1 nao afeta o que HOMOLOGATOR ve."""
        false_permission(self.user, self.company, self.model, allowed="subcompany")
        uuids_before = set(self._api_uuids(client, self.token))

        engie2 = User.objects.get(uuid=ENGIE2_UUID)
        firm_a1 = Firm.objects.get(uuid=FIRM_A1)
        firm_a1.users.add(engie2)

        uuids_after = set(self._api_uuids(client, self.token))
        assert uuids_before == uuids_after
