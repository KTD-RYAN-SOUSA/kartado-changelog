from datetime import date

from apps.bim.utils import delete_bim_models_by_company
from apps.companies.models import Company, UserInCompany
from helpers.strings import get_obj_from_path


def deactivates_expired_users():
    current_date = date.today()
    for user_in_company in UserInCompany.objects.all().only(
        "expiration_date", "is_active"
    ):
        if (
            user_in_company.expiration_date
            and current_date > user_in_company.expiration_date
        ):
            user_in_company.is_active = False
            user_in_company.save()


def cleanup_bim_models_for_disabled_companies():
    """
    Processa limpeza de modelos BIM para companies onde can_bim_view = False.

    Roda periodicamente (a cada 5 minutos) via Zappa scheduled event.
    Verifica companies que possuem BIM models mas tem can_bim_view desabilitado.

    Processa no máximo 10 companies por execução para evitar timeouts.
    """
    from apps.bim.models import BIMModel

    # Limite de companies processadas por execução (evita timeouts)
    MAX_COMPANIES_PER_RUN = 10

    # Buscar companies com BIM models (apenas campos necessários)
    companies_with_bim = (
        Company.objects.filter(bim_models__isnull=False)
        .distinct()
        .only("uuid", "custom_options")[:MAX_COMPANIES_PER_RUN]
    )

    cleaned_count = 0

    for company in companies_with_bim:
        custom_options = company.custom_options or {}

        # Verificar se can_bim_view existe e está False
        can_bim_view = get_obj_from_path(custom_options, "metadata__can_bim_view")

        # Se can_bim_view for explicitamente False, deletar modelos BIM
        if can_bim_view is False:
            # Usar exists() ao invés de count() (mais eficiente)
            if BIMModel.objects.filter(company=company).exists():
                delete_bim_models_by_company(company)
                cleaned_count += 1

    return cleaned_count


# Zappa alias: function path must be ≤63 chars (0.61.x validation)
def cleanup_bim_disabled_companies():
    return cleanup_bim_models_for_disabled_companies()
