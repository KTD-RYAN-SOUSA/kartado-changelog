import pytest

from apps.companies.models import Company
from apps.users.models import User
from helpers.strings import to_snake_case


@pytest.mark.urls("RoadLabsAPI.urls.base")
class TestBase(object):
    user: User
    company: Company
    token: str

    @pytest.fixture(autouse=True)
    def _initial(self, initial_data):
        self.user, self.company, self.token = initial_data
        false_permission(self.user, self.company, self.model, all_true=True)


def false_permission(user, company, model, allowed="all", all_true=False):
    user_permissions = user.companies_membership.filter(
        company=company, permissions__name="HOMOLOGATOR"
    ).first()
    permissions = user_permissions.permissions

    if model in permissions.permissions:
        get_model = permissions.permissions[model]
    elif to_snake_case(model) in permissions.permissions:
        get_model = permissions.permissions[to_snake_case(model)]
    else:
        get_model = {
            "can_edit": True,
            "can_view": True,
            "can_create": True,
            "can_delete": True,
            "can_approve": True,
            "can_deny": True,
            "queryset": "all",
        }

    if all_true:
        for key, value in get_model.items():
            if "can" in key:
                get_model[key] = True
            if "query" in key:
                get_model[key] = allowed
    else:
        for key, value in get_model.items():
            if allowed == "all":
                if "can" in key:
                    get_model[key] = False
            else:
                if "can" in key:
                    get_model[key] = True
            if "query" in key:
                get_model[key] = allowed

    permissions.permissions[model] = get_model
    permissions.save()

    return True


def add_false_permission(user, company, model, new_permission):
    user_permissions = user.companies_membership.filter(
        company=company, permissions__name="HOMOLOGATOR"
    ).first()
    permissions = user_permissions.permissions
    permissions.permissions[model].update(new_permission)
    permissions.save()
