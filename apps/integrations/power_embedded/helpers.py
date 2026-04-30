import logging
import os
import re

from apps.companies.models import Company, UserInCompany
from helpers.aws import get_power_embedded_credentials
from helpers.strings import clean_latin_string
from RoadLabsAPI.settings import credentials

logger = logging.getLogger(__name__)


def get_credentials():
    try:
        stage = credentials.stage.upper()
        return get_power_embedded_credentials(stage)
    except Exception:
        return {
            "api_key": os.environ.get("POWER_EMBEDDED_API_KEY", ""),
            "base_url": os.environ.get("POWER_EMBEDDED_BASE_URL", ""),
            "organization_id": os.environ.get("POWER_EMBEDDED_ORGANIZATION_ID", ""),
        }


def normalize_name(name):
    cleaned = clean_latin_string(name).lower()
    cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned)
    return re.sub(r"\s+", "_", cleaned).strip("_")


def build_group_name(user, company):
    membership = (
        UserInCompany.objects.filter(user=user, company=company, is_active=True)
        .select_related("permissions")
        .first()
    )

    if not membership or not membership.permissions:
        return None

    permission_slug = normalize_name(membership.permissions.name)
    company_slug = normalize_name(company.name)
    return f"{permission_slug}_{company_slug}"


def get_group_for_company(client, user, company_id):
    try:
        company = Company.objects.get(uuid=company_id)
    except Company.DoesNotExist:
        return None

    group_name = build_group_name(user, company)
    if not group_name:
        return None

    return client.get_group_by_name(group_name)


def ensure_user_in_pe(client, user, group_id):
    pe_user = client.get_user_by_email(user.email)

    if not pe_user:
        full_name = user.get_full_name() or user.email
        client.create_user(email=user.email, name=full_name)
        client.link_user_to_groups(email=user.email, group_ids=[group_id])
        return "created"

    user_groups = pe_user.get("groups") or []
    if group_id not in user_groups:
        client.link_user_to_groups(email=user.email, group_ids=[group_id])
        return "linked"

    return "already_linked"
