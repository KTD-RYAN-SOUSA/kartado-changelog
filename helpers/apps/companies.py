from apps.companies.const.app_types import ENERGY
from apps.companies.models import Company


def is_energy_company(company: Company) -> bool:
    mobile_app = company.mobile_app_override or (
        company.company_group.mobile_app if company.company_group else None
    )

    return mobile_app == ENERGY
