"""
Auto-scheduling core functionality.

This module contains the core logic for automatically allocating Reportings to Jobs
based on company-specific rules and configurations.
"""

import logging
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.service_orders.models import ServiceOrderActionStatusSpecs
from apps.work_plans.models import Job

logger = logging.getLogger(__name__)


class RuleMatcher(ABC):
    @abstractmethod
    def matches(self, reporting, rule) -> bool:
        ...


class OccurrenceTypeMatcher(RuleMatcher):
    def matches(self, reporting, rule) -> bool:
        match_value = rule.get("match_value")

        if not match_value:
            logger.warning(f"Regra occurrence_type sem match_value: {rule}")
            return False
        matched = str(reporting.occurrence_type_id) == str(match_value)

        return matched


class OccurrenceKindMatcher(RuleMatcher):
    def matches(self, reporting, rule) -> bool:
        match_value = rule.get("match_value")

        if not match_value:
            logger.warning(f"Regra occurrence_kind sem match_value: {rule}")
            return False
        if reporting.occurrence_type:
            matched = reporting.occurrence_type.occurrence_kind == match_value
            return matched

        return False


class FormFieldMatcher(RuleMatcher):
    def matches(self, reporting, rule) -> bool:
        field_api_name = rule.get("field_api_name")
        field_value_to_match = rule.get("field_value")

        if not field_api_name or field_value_to_match is None:
            logger.warning(
                f"Regra form_field inválida (faltando field_api_name ou field_value): {rule}"
            )
            return False

        field_value = reporting.form_data.get(field_api_name)

        if field_value is not None:
            if isinstance(field_value, list):
                matched = field_value_to_match in field_value
            else:
                matched = str(field_value) == str(field_value_to_match)
            return matched

        return False


class RuleMatcherFactory:
    _matchers = {
        "occurrence_type": OccurrenceTypeMatcher,
        "occurrence_kind": OccurrenceKindMatcher,
        "form_field": FormFieldMatcher,
    }

    @classmethod
    def create(cls, match_type: str) -> "RuleMatcher | None":
        matcher_class = cls._matchers.get(match_type)
        if not matcher_class:
            return None
        return matcher_class()


def process_auto_scheduling(reporting: Any) -> None:
    """
    Processa o auto-scheduling de um Reporting, alocando-o automaticamente em um Job.

    Esta função implementa a lógica de alocação automática de Reportings em Jobs
    baseada em regras configuradas por company. O processo inclui:

    1. Verificação de habilitação do auto-scheduling
    2. Verificação de elegibilidade do Reporting
    3. Match de regras (occurrence_type, occurrence_kind, form_field)
    4. Busca ou criação de Job apropriado
    5. Vinculação do Reporting ao Job
    6. Atualização de status e watchers

    Args:
        reporting: Instância de Reporting a ser processada

    Returns:
        None

    Note:
        - A função é idempotente e pode ser chamada múltiplas vezes
        - Reportings já vinculados a Jobs são ignorados
        - Usa transaction.atomic() para garantir consistência
    """
    # Passo 1 - Obter config
    config = reporting.company.metadata.get("auto_scheduling_jobs", {})
    if not config.get("enabled", False):
        logger.debug(
            f"Auto-scheduling desabilitado para company {reporting.company_id}"
        )
        return

    # Passo 2 - Verificar elegibilidade
    if reporting.job_id is not None:
        logger.debug(
            f"Reporting {reporting.uuid} já está vinculado ao Job {reporting.job_id}"
        )
        return

    activation_date_str = config.get("activation_date")
    if not activation_date_str:
        logger.warning(
            f"Auto-scheduling habilitado mas sem activation_date para company {reporting.company_id}"
        )
        return

    activation_date = parse_datetime(activation_date_str)
    if not activation_date:
        logger.error(
            f"Formato inválido de activation_date: {activation_date_str} "
            f"para company {reporting.company_id}"
        )
        return

    if reporting.created_at < activation_date:
        logger.debug(
            f"Reporting {reporting.uuid} criado antes da data de ativação "
            f"({reporting.created_at} < {activation_date})"
        )
        return

    if reporting.firm is None:
        logger.warning(
            f"Reporting {reporting.uuid} não possui firm associada, "
            f"ignorando auto-scheduling"
        )
        return

    # Passo 3 - Match de regras
    rules = config.get("rules", [])
    if not rules:
        logger.debug(
            f"Nenhuma regra de auto-scheduling configurada para company {reporting.company_id}"
        )
        return

    matched_rule = None
    for rule in rules:
        match_type = rule.get("match_type")

        if not match_type:
            logger.warning(f"Regra inválida (faltando match_type): {rule}")
            continue

        matcher = RuleMatcherFactory.create(match_type=match_type)
        if matcher is None:
            logger.warning(f"Tipo de regra desconhecido: {match_type}, ignorando")
            continue
        matched = matcher.matches(reporting=reporting, rule=rule)

        if matched:
            matched_rule = rule
            logger.debug(f"Reporting {reporting.uuid} matched regra: {rule}")
            break

    if not matched_rule:
        logger.debug(
            f"Reporting {reporting.uuid} não deu match em nenhuma regra de auto-scheduling"
        )
        return

    deadline_days = matched_rule.get("deadline_days", 7)

    # Passos 4-7 devem estar dentro de transaction.atomic
    with transaction.atomic():
        # Passo 4 - Buscar Job válido
        now = timezone.localtime()
        window_start = now - timedelta(days=config.get("search_window_days", 7))
        max_reportings = config.get("max_reportings_per_job", 100)

        job = (
            Job.objects.select_for_update()
            .filter(
                company=reporting.company,
                firm=reporting.firm,
                start_date__gte=window_start,
                end_date__gte=now,
                reporting_count__lt=max_reportings,
                archived=False,
            )
            .order_by("reporting_count", "-start_date")
            .first()
        )

        # Passo 5 - Vincular ou criar Job
        created_new = False

        if job:
            if not job.has_auto_allocated_reportings:
                job.has_auto_allocated_reportings = True
                job.save(update_fields=["has_auto_allocated_reportings"])
        else:
            # Criar novo Job
            created_new = True
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = today + timedelta(
                days=deadline_days, hours=23, minutes=59, seconds=59
            )
            firm_name = reporting.firm.name if reporting.firm else "Sem Equipe"
            description = f"[{today.strftime('%d/%m')}] - {firm_name} - Automática"
            title = description

            job = Job(
                company=reporting.company,
                firm=reporting.firm,
                start_date=today,
                end_date=end_date,
                description=description,
                title=title,
                is_automatic=True,
                has_auto_allocated_reportings=True,
                created_by=reporting.created_by,
                worker=reporting.created_by,
            )
            job.save()  # number será gerado pelo signal pre_save job_name_format

        # Passo 6 - Vincular Reporting e atualizar status
        # Seguindo o padrão de helpers/apps/job.py
        in_job_status_spec = ServiceOrderActionStatusSpecs.objects.filter(
            company=reporting.company, order=2
        ).first()

        if in_job_status_spec:
            lower_status_ids = (
                ServiceOrderActionStatusSpecs.objects.filter(
                    company=reporting.company, order__lt=2
                )
                .distinct()
                .values_list("status_id", flat=True)
            )
            if reporting.status_id in lower_status_ids:
                reporting.status = in_job_status_spec.status

        reporting.job = job
        reporting.firm = job.firm
        reporting.save()

        # Passo 7 - Adicionar watchers
        if reporting.created_by:
            job.watcher_users.add(reporting.created_by)
        if reporting.firm:
            job.watcher_firms.add(reporting.firm)

    # Passo 8 - Log
    logger.info(
        f"Auto-scheduling: Reporting {reporting.uuid} alocado no Job {job.uuid} "
        f"(company={reporting.company_id}, {'novo' if created_new else 'existente'})"
    )

    # Passo 9 - Evento Amplitude
    _track_amplitude_event(reporting)


def _get_user_permission_name(user, company):
    """Retorna o nome do UserPermission do usuário na company."""
    from apps.companies.models import UserInCompany

    try:
        uic = UserInCompany.objects.select_related("permissions").get(
            user=user, company=company
        )
        if uic.permissions:
            return uic.permissions.name
    except UserInCompany.DoesNotExist:
        pass

    return ""


def _track_amplitude_event(reporting):
    """Envia evento 'programação automática' para o Amplitude.

    Silencioso em caso de falha — nunca propaga exceções para não
    afetar o fluxo principal de auto-scheduling.
    """
    try:
        from helpers.amplitude import track_event

        if not reporting.created_by:
            return

        permission_name = _get_user_permission_name(
            reporting.created_by, reporting.company
        )

        company_group_name = ""
        if reporting.company.company_group:
            company_group_name = reporting.company.company_group.name

        track_event(
            user_id=reporting.created_by.uuid,
            event_type="programação automática",
            event_properties={
                "unidade": reporting.company.name,
                "grupo_da_unidade": company_group_name,
                "nome_completo": reporting.created_by.get_full_name(),
                "nivel_de_permissao": permission_name,
            },
        )
    except Exception:
        logger.exception(
            f"Erro ao enviar evento Amplitude para reporting {reporting.uuid}"
        )
