"""
Testes para a funcionalidade de Auto-Scheduling de Reportings em Jobs.

Este módulo testa a função `process_auto_scheduling` de `helpers/apps/auto_scheduling.py`,
que implementa a lógica de alocação automática de Reportings em Jobs baseada em
regras configuradas por company.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db.models import QuerySet
from django.utils import timezone

from apps.companies.models import Firm
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting
from apps.service_orders.models import ServiceOrderActionStatusSpecs
from apps.work_plans.models import Job
from helpers.apps.auto_scheduling import process_auto_scheduling

pytestmark = pytest.mark.django_db


def _noop_select_for_update(self, **kwargs):
    """Mock select_for_update para evitar deadlock em testes."""
    return self


@pytest.fixture(autouse=True)
def mock_select_for_update():
    """Desabilita select_for_update em todos os testes deste módulo."""
    with patch.object(QuerySet, "select_for_update", _noop_select_for_update):
        yield


@pytest.fixture
def auto_scheduling_setup(initial_data):
    """
    Setup base para testes de auto-scheduling.

    Retorna um dict com objetos necessários para os testes:
    - user, company, token
    - reporting_base (um Reporting existente no banco de fixtures)
    - firm (uma Firm existente no banco de fixtures)
    - occurrence_type (um OccurrenceType existente no banco de fixtures)
    - status_order_1 (status com order=1)
    - status_order_2 (status com order=2)
    """
    user, company, token = initial_data

    # Buscar objetos existentes do banco de fixtures
    reporting_base = Reporting.objects.filter(company=company).first()
    firm = Firm.objects.filter(company=company).first()
    occurrence_type = OccurrenceType.objects.filter(company=company).first()

    # Buscar status specs
    status_order_1 = ServiceOrderActionStatusSpecs.objects.filter(
        company=company, order=1
    ).first()
    status_order_2 = ServiceOrderActionStatusSpecs.objects.filter(
        company=company, order=2
    ).first()

    return {
        "user": user,
        "company": company,
        "token": token,
        "reporting_base": reporting_base,
        "firm": firm,
        "occurrence_type": occurrence_type,
        "status_order_1": status_order_1,
        "status_order_2": status_order_2,
    }


# =============================================================================
# GRUPO A — Early Returns (não deve alocar)
# =============================================================================


class TestAutoSchedulingEarlyReturns:
    """Grupo A - Cenários que devem retornar sem alocar."""

    def test_config_disabled_should_not_allocate(self, auto_scheduling_setup):
        """Config desabilitada (enabled=False) não deve alocar."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-disabled",
        )

        # Configurar auto_scheduling APÓS criar o Reporting
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": False,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is None

    def test_no_config_should_not_allocate(self, auto_scheduling_setup):
        """Config não existe (company sem auto_scheduling_jobs) não deve alocar."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-no-config",
        )

        # Garantir que não há config
        if "auto_scheduling_jobs" in company.metadata:
            del company.metadata["auto_scheduling_jobs"]
            company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is None

    def test_reporting_already_with_job_should_not_reallocate(
        self, auto_scheduling_setup
    ):
        """Reporting já com job vinculado não deve ser realocado."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        # Criar Job existente
        existing_job = Job.objects.create(
            company=company,
            firm=firm,
            start_date=timezone.now(),
            description="Job existente",
            created_by=user,
        )

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-already-job",
            job=existing_job,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id == existing_job.uuid

    def test_reporting_before_activation_date_should_not_allocate(
        self, auto_scheduling_setup
    ):
        """Reporting criado antes de activation_date não deve alocar."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status

        # Criar reporting com created_at no passado (via raw save)
        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-before-activation",
        )

        # Setar activation_date no futuro
        activation_date = timezone.now() + timedelta(days=1)
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": activation_date.isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is None

    def test_no_rule_match_should_not_allocate(self, auto_scheduling_setup):
        """Nenhuma regra bate com o Reporting não deve alocar."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status

        # Criar outro occurrence_type
        other_occurrence_type = (
            OccurrenceType.objects.filter(company=company)
            .exclude(uuid=occurrence_type.uuid)
            .first()
        )

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-no-match",
        )

        # Configurar regra com outro occurrence_type
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(other_occurrence_type.uuid)
                    if other_occurrence_type
                    else "fake-uuid",
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is None

    def test_reporting_without_firm_should_not_allocate(self, auto_scheduling_setup):
        """Reporting sem firm não deve alocar (deve logar warning)."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=None,  # SEM firm
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-no-firm",
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is None


# =============================================================================
# GRUPO B — Match de Regras
# =============================================================================


class TestAutoSchedulingRuleMatching:
    """Grupo B - Cenários de match de regras."""

    def test_match_by_occurrence_type_uuid(self, auto_scheduling_setup):
        """Match por occurrence_type (comparação de UUID) deve alocar."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-match-uuid",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is not None

    def test_match_by_occurrence_kind(self, auto_scheduling_setup):
        """Match por occurrence_kind (comparação de texto) deve alocar."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-match-kind",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_kind",
                    "match_value": occurrence_type.occurrence_kind,
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is not None

    def test_match_by_form_field_string_value(self, auto_scheduling_setup):
        """Match por form_field com valor string direta deve alocar."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-match-form-string",
            created_by=user,
            form_data={"priority": "high"},
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "form_field",
                    "field_api_name": "priority",
                    "field_value": "high",
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is not None

    def test_match_by_form_field_array_value(self, auto_scheduling_setup):
        """Match por form_field com valor array deve alocar."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-match-form-array",
            created_by=user,
            form_data={"tags": ["urgent", "safety", "maintenance"]},
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "form_field",
                    "field_api_name": "tags",
                    "field_value": "safety",
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is not None


# =============================================================================
# GRUPO C — Alocação em Job Existente
# =============================================================================


class TestAutoSchedulingExistingJob:
    """Grupo C - Alocação em Job existente."""

    def test_prioritize_job_with_lower_reporting_count(self, auto_scheduling_setup):
        """Prioriza Job com menor reporting_count."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        # Criar Job com reporting_count=5
        Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            end_date=now + timedelta(days=7),
            description="Job com 5",
            created_by=user,
            reporting_count=5,
        )

        # Criar Job com reporting_count=2 (deve ser escolhido)
        job_with_2 = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            end_date=now + timedelta(days=7),
            description="Job com 2",
            created_by=user,
            reporting_count=2,
        )

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-lower-count",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id == job_with_2.uuid

    def test_tiebreak_prioritize_most_recent_job(self, auto_scheduling_setup):
        """Desempate: prioriza Job mais recente (start_date DESC)."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        # Criar Job mais antigo
        Job.objects.create(
            company=company,
            firm=firm,
            start_date=now - timedelta(days=2),
            end_date=now + timedelta(days=7),
            description="Job antigo",
            created_by=user,
            reporting_count=3,
        )

        # Criar Job mais recente (deve ser escolhido)
        job_new = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            end_date=now + timedelta(days=7),
            description="Job recente",
            created_by=user,
            reporting_count=3,  # mesmo reporting_count
        )

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-tiebreak",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=3)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id == job_new.uuid

    def test_does_not_select_job_at_max_reportings(self, auto_scheduling_setup):
        """Não seleciona Job com reporting_count >= max_reportings_per_job."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        # Criar Job com reporting_count no limite
        job_full = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            end_date=now + timedelta(days=7),
            description="Job cheio",
            created_by=user,
            reporting_count=10,  # no limite
        )

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-max-reportings",
            created_by=user,
        )

        # Configurar auto_scheduling com max_reportings_per_job=10
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "max_reportings_per_job": 10,
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        # Deve criar um novo Job, não usar o cheio
        assert reporting.job_id is not None
        assert reporting.job_id != job_full.uuid

    def test_does_not_select_expired_job(self, auto_scheduling_setup):
        """Não seleciona Job com end_date < hoje."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        # Criar Job expirado
        job_expired = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now - timedelta(days=10),
            end_date=now - timedelta(days=1),  # expirado
            description="Job expirado",
            created_by=user,
            reporting_count=2,
        )

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-expired",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=11)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        # Deve criar um novo Job, não usar o expirado
        assert reporting.job_id is not None
        assert reporting.job_id != job_expired.uuid

    def test_does_not_select_archived_job(self, auto_scheduling_setup):
        """Não seleciona Job com archived=True."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        # Criar Job arquivado
        job_archived = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            end_date=now + timedelta(days=7),
            description="Job arquivado",
            created_by=user,
            reporting_count=2,
            archived=True,  # arquivado
        )

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-archived",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        # Deve criar um novo Job, não usar o arquivado
        assert reporting.job_id is not None
        assert reporting.job_id != job_archived.uuid

    def test_sets_has_auto_allocated_reportings_on_existing_job(
        self, auto_scheduling_setup
    ):
        """Seta has_auto_allocated_reportings=True no Job existente."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        # Criar Job manual (has_auto_allocated_reportings=False)
        job_manual = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            end_date=now + timedelta(days=7),
            description="Job manual",
            created_by=user,
            reporting_count=2,
            has_auto_allocated_reportings=False,
        )

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-set-flag",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        job_manual.refresh_from_db()
        assert reporting.job_id == job_manual.uuid
        assert job_manual.has_auto_allocated_reportings is True


# =============================================================================
# GRUPO D — Criação de Novo Job
# =============================================================================


class TestAutoSchedulingNewJob:
    """Grupo D - Criação de novo Job."""

    def test_new_job_has_correct_flags(self, auto_scheduling_setup):
        """Campos corretos: is_automatic=True, has_auto_allocated_reportings=True."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-new-job-flags",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is not None

        job = Job.objects.get(uuid=reporting.job_id)
        assert job.is_automatic is True
        assert job.has_auto_allocated_reportings is True

    def test_new_job_description_format(self, auto_scheduling_setup):
        """description no formato [DD/MM] - {firm_name} - Automática."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-new-job-desc",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        job = Job.objects.get(uuid=reporting.job_id)

        local_now = timezone.localtime(now)
        today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        expected_description = f"[{today.strftime('%d/%m')}] - {firm.name} - Automática"
        assert job.description == expected_description

    def test_new_job_dates(self, auto_scheduling_setup):
        """start_date = hoje, end_date = hoje + deadline_days (23:59:59)."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-new-job-dates",
            created_by=user,
        )

        # Configurar auto_scheduling com deadline_days=5
        deadline_days = 5
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": deadline_days,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        job = Job.objects.get(uuid=reporting.job_id)

        local_now = timezone.localtime(now)
        today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        expected_end_date = today + timedelta(
            days=deadline_days, hours=23, minutes=59, seconds=59
        )

        assert job.start_date == today
        local_end_date = timezone.localtime(job.end_date)
        assert local_end_date.date() == expected_end_date.date()
        assert local_end_date.hour == 23
        assert local_end_date.minute == 59
        assert local_end_date.second == 59

    def test_new_job_created_by(self, auto_scheduling_setup):
        """created_by = reporting.created_by."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-new-job-creator",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        job = Job.objects.get(uuid=reporting.job_id)
        assert job.created_by == user


# =============================================================================
# GRUPO E — Pós-Alocação
# =============================================================================


class TestAutoSchedulingPostAllocation:
    """Grupo E - Verificações pós-alocação."""

    def test_reporting_job_is_set(self, auto_scheduling_setup):
        """reporting.job está setado corretamente."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-job-set",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is not None
        assert isinstance(reporting.job, Job)

    def test_status_updated_when_order_less_than_2(self, auto_scheduling_setup):
        """Status atualizado para order=2 quando status anterior era order < 2."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status_order_1 = auto_scheduling_setup["status_order_1"]
        status_order_2 = auto_scheduling_setup["status_order_2"]
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status_order_1.status,  # order=1
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-status-update",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.status_id == status_order_2.status_id

    def test_watchers_added(self, auto_scheduling_setup):
        """Watchers: created_by adicionado a watcher_users e firm adicionado a watcher_firms."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-watchers",
            created_by=user,
        )

        # Configurar auto_scheduling
        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        job = Job.objects.get(uuid=reporting.job_id)

        assert user in job.watcher_users.all()
        assert firm in job.watcher_firms.all()


# =============================================================================
# GRUPO F — Filtro no JobFilter
# =============================================================================


class TestAutoSchedulingFilter:
    """Grupo F - Filtro no JobFilter."""

    def test_filter_auto_scheduling_true_returns_automatic_jobs(
        self, auto_scheduling_setup, client
    ):
        """auto_scheduling=True retorna Jobs com is_automatic=True ou has_auto_allocated_reportings=True."""
        # Arrange
        company = auto_scheduling_setup["company"]
        firm = auto_scheduling_setup["firm"]
        user = auto_scheduling_setup["user"]
        token = auto_scheduling_setup["token"]

        now = timezone.now()

        # Criar Job 100% automático
        job_auto = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            description="Job automático",
            created_by=user,
            is_automatic=True,
            has_auto_allocated_reportings=True,
        )

        # Criar Job manual com reportings auto-alocados
        job_mixed = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            description="Job misto",
            created_by=user,
            is_automatic=False,
            has_auto_allocated_reportings=True,
        )

        # Criar Job 100% manual
        job_manual = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            description="Job manual",
            created_by=user,
            is_automatic=False,
            has_auto_allocated_reportings=False,
        )

        # Act
        response = client.get(
            path=f"/Job/?company={company.pk}&auto_scheduling=True",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        job_uuids = [item["id"] for item in data["data"]]
        assert str(job_auto.uuid) in job_uuids
        assert str(job_mixed.uuid) in job_uuids
        assert str(job_manual.uuid) not in job_uuids

    def test_filter_auto_scheduling_false_returns_manual_jobs(
        self, auto_scheduling_setup, client
    ):
        """auto_scheduling=False retorna apenas Jobs 100% manuais."""
        # Arrange
        company = auto_scheduling_setup["company"]
        firm = auto_scheduling_setup["firm"]
        user = auto_scheduling_setup["user"]
        token = auto_scheduling_setup["token"]

        now = timezone.now()

        # Criar Job 100% automático
        job_auto = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            description="Job automático",
            created_by=user,
            is_automatic=True,
            has_auto_allocated_reportings=True,
        )

        # Criar Job manual com reportings auto-alocados
        job_mixed = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            description="Job misto",
            created_by=user,
            is_automatic=False,
            has_auto_allocated_reportings=True,
        )

        # Criar Job 100% manual
        job_manual = Job.objects.create(
            company=company,
            firm=firm,
            start_date=now,
            description="Job manual",
            created_by=user,
            is_automatic=False,
            has_auto_allocated_reportings=False,
        )

        # Act
        response = client.get(
            path=f"/Job/?company={company.pk}&auto_scheduling=False",
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        job_uuids = [item["id"] for item in data["data"]]
        assert str(job_auto.uuid) not in job_uuids
        assert str(job_mixed.uuid) not in job_uuids
        assert str(job_manual.uuid) in job_uuids


# =============================================================================
# GRUPO G — Testes de Integração (Signal e Import)
# =============================================================================


class TestAutoSchedulingSignalIntegration:
    """Grupo G - Testes de integração com signal post_save."""

    def test_signal_auto_schedules_new_reporting(self, auto_scheduling_setup):
        """Criar Reporting via ORM dispara signal"""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act - signal post_save é disparado automaticamente
        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-signal-create",
            created_by=user,
        )

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is not None

    def test_signal_does_not_schedule_when_config_disabled(self, auto_scheduling_setup):
        """Signal não aloca quando config desabilitada."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        company.metadata["auto_scheduling_jobs"] = {
            "enabled": False,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [],
        }
        company.save()

        # Act
        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-signal-disabled",
            created_by=user,
        )

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is None


# =============================================================================
# GRUPO F — Evento Amplitude
# =============================================================================


class TestAutoSchedulingAmplitudeEvent:
    """Grupo F - Evento Amplitude após alocação bem-sucedida."""

    @patch("helpers.amplitude.track_event")
    def test_amplitude_event_sent_on_success(
        self, mock_track_event, auto_scheduling_setup
    ):
        """Evento Amplitude deve ser enviado após alocação bem-sucedida."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-amplitude-success",
            created_by=user,
        )

        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is not None
        mock_track_event.assert_called_once()

        call_kwargs = mock_track_event.call_args
        assert call_kwargs[1]["event_type"] == "programação automática"
        assert call_kwargs[1]["user_id"] == user.uuid

    @patch("helpers.amplitude.track_event")
    def test_amplitude_event_properties(self, mock_track_event, auto_scheduling_setup):
        """Propriedades do evento devem conter unidade, grupo, nome e permissão."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-amplitude-props",
            created_by=user,
        )

        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        call_kwargs = mock_track_event.call_args[1]
        event_props = call_kwargs["event_properties"]

        assert event_props["unidade"] == company.name
        assert event_props["nome_completo"] == user.get_full_name()
        assert "grupo_da_unidade" in event_props
        assert "nivel_de_permissao" in event_props

    @patch("helpers.amplitude.track_event")
    def test_amplitude_event_permission_name(
        self, mock_track_event, auto_scheduling_setup
    ):
        """nivel_de_permissao deve conter o nome do UserPermission."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-amplitude-perm",
            created_by=user,
        )

        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        call_kwargs = mock_track_event.call_args[1]
        event_props = call_kwargs["event_properties"]

        # O fixture initial_data cria UserInCompany com UserPermission name="HOMOLOGATOR"
        assert event_props["nivel_de_permissao"] == "HOMOLOGATOR"

    @patch("helpers.amplitude.track_event")
    def test_amplitude_event_not_sent_when_disabled(
        self, mock_track_event, auto_scheduling_setup
    ):
        """Evento NÃO deve ser enviado quando auto-scheduling está desabilitado."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-amplitude-disabled",
        )

        company.metadata["auto_scheduling_jobs"] = {
            "enabled": False,
            "activation_date": (timezone.now() - timedelta(days=1)).isoformat(),
            "rules": [],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        mock_track_event.assert_not_called()

    @patch("helpers.amplitude.track_event")
    def test_amplitude_event_not_sent_when_no_match(
        self, mock_track_event, auto_scheduling_setup
    ):
        """Evento NÃO deve ser enviado quando nenhuma regra deu match."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status
        user = auto_scheduling_setup["user"]

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-amplitude-no-match",
            created_by=user,
        )

        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": "00000000-0000-0000-0000-000000000000",
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is None
        mock_track_event.assert_not_called()

    @patch("helpers.amplitude.track_event")
    def test_amplitude_event_not_sent_when_no_created_by(
        self, mock_track_event, auto_scheduling_setup
    ):
        """Evento NÃO deve ser enviado quando reporting não tem created_by."""
        # Arrange
        company = auto_scheduling_setup["company"]
        reporting_base = auto_scheduling_setup["reporting_base"]
        firm = auto_scheduling_setup["firm"]
        occurrence_type = auto_scheduling_setup["occurrence_type"]
        status = auto_scheduling_setup["status_order_1"].status

        now = timezone.now()

        reporting = Reporting.objects.create(
            company=company,
            occurrence_type=occurrence_type,
            firm=firm,
            status=status,
            km=reporting_base.km,
            direction=reporting_base.direction,
            lane=reporting_base.lane,
            number="test-amplitude-no-user",
            created_by=None,
        )

        company.metadata["auto_scheduling_jobs"] = {
            "enabled": True,
            "activation_date": (now - timedelta(days=1)).isoformat(),
            "rules": [
                {
                    "match_type": "occurrence_type",
                    "match_value": str(occurrence_type.uuid),
                    "deadline_days": 7,
                }
            ],
        }
        company.save()

        # Act
        process_auto_scheduling(reporting)

        # Assert
        reporting.refresh_from_db()
        assert reporting.job_id is not None
        mock_track_event.assert_not_called()
