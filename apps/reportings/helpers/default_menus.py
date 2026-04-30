from typing import List
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.db.models import Max, Q
from django_bulk_update.helper import bulk_update

from apps.companies.models import Company
from apps.occurrence_records.models import RecordPanelShowList
from apps.reportings.models import RecordMenu, RecordMenuRelation
from apps.users.models import User
from helpers.apps.companies import is_energy_company
from helpers.histories import bulk_update_with_history


def create_user_menu(user: User, company: Company):
    """
    Creates RecordMenuRelation for a User in a Company for non-system default RecordMenus.

    This function creates RecordMenuRelation entries for all RecordMenus in the company that
    the User doesn't already have access to. The first 9 RecordMenus are set as visible,
    while any additional RecordMenus are hidden by default.

    Args:
        User (User): The User to create RecordMenuRelation for
        company (Company): The company containing the RecordMenus
    """

    record_menus = (
        RecordMenu.objects.filter(company=company)
        .exclude(recordmenurelation__user=user)
        .exclude(system_default=True)
        .order_by("name")
    )
    user_order = get_user_max_order(user, company)
    user_menus = []
    for index, rm in enumerate(record_menus, start=1):
        user_menus.append(
            RecordMenuRelation(
                user=user,
                hide_menu=False if index <= 9 else True,
                order=user_order,
                record_menu=rm,
                company=company,
            )
        )
        user_order += 1

    RecordMenuRelation.objects.bulk_create(user_menus)


def get_user_max_order(user: User, company: Company) -> int:
    """
    Gets the highest order value for a user's visible non-system RecordMenuRelation.

    Retrieves the maximum order value from RecordMenuRelation entries that are:
    - Associated with the given user and company
    - Not hidden (hide_menu=False)
    - Not system default RecordMenus

    Args:
        user (User): The user to get max order for
        company (Company): The company context for RecordMenuRelation

    Returns:
        int: The next available order value (max + 1), or 0 if no visible menus exist
    """

    max_order = RecordMenuRelation.objects.filter(
        company=company, user=user, hide_menu=False, record_menu__system_default=False
    ).aggregate(Max("order"))
    user_max_order = max_order.get("order__max")

    return user_max_order + 1 if user_max_order is not None else 0


def rebalance_visible_menus_orders(user_id: str, company_id: str):
    """This is needed when we hide a menu since there will be a hole in the order of the remaining visible menus"""

    relations = (
        RecordMenuRelation.objects.filter(
            hide_menu=False,
            company_id=company_id,
            user_id=user_id,
            record_menu__system_default=False,
        )
        .order_by("order")
        .only("uuid", "order")
    )

    updated_relations = []
    new_order = 0
    for relation in relations:
        if relation.order != new_order:
            relation.order = new_order
            updated_relations.append(relation)

        new_order += 1

    if updated_relations:
        bulk_update_with_history(
            objs=updated_relations, model=RecordMenuRelation, use_django_bulk=True
        )


def rebalance_visible_panels_orders(user_id: str, company_id: str, menu_id: str = None):
    """This is needed when we hide a panel since there will be a hole in the order of the remaining visible panels"""

    filters = {
        "user_id": user_id,
        "panel__company_id": company_id,
    }
    if menu_id:
        filters["panel__menu_id"] = menu_id
    relations = (
        RecordPanelShowList.objects.filter(**filters)
        .order_by("order")
        .only("uuid", "order")
    )

    updated_panels = []
    new_order = 1
    for panel in relations:
        if panel.order != new_order:
            panel.order = new_order
            updated_panels.append(panel)

        new_order += 1

    if updated_panels:
        bulk_update(updated_panels, update_fields=["order"])


def create_users_record_menu(
    record_menu: RecordMenu,
    users_id: List[UUID],
    company: Company,
    users_to_exclude: List[UUID] = [],
):
    """
    Creates RecordMenuRelation entries for multiple Users with a given RecordMenu.

    This function creates RecordMenuRelations for a list of Users, calculating the appropriate
    order value for each User based on their existing visible RecordMenus.

    Args:
        record_menu (RecordMenu): The RecordMenu to create relationships for
        users_id (List[UUID]): List of User UUIDs to create relationships for
        company (Company): The company context for the RecordMenuRelations
        users_to_exclude (List[UUID], optional): List of User UUIDs to exclude. Defaults to [].

    """

    active_users = User.objects.filter(uuid__in=users_id,).annotate(
        max_order=Max(
            "recordmenurelation__order",
            filter=Q(
                recordmenurelation__company=company, recordmenurelation__hide_menu=False
            ),
        )
    )
    if users_to_exclude:
        active_users = active_users.exclude(uuid__in=users_to_exclude)
    record_menu_relation_entries = []
    for user_instance in active_users:
        record_menu_relation_entries.append(
            RecordMenuRelation(
                record_menu=record_menu,
                user=user_instance,
                order=user_instance.max_order + 1
                if isinstance(user_instance.max_order, int)
                else 0,
                company=company,
                hide_menu=True,
            )
        )

    RecordMenuRelation.objects.bulk_create(record_menu_relation_entries)
    record_menu.set_max_order()


def create_company_menus(company: Company):
    """
    Creates default system and RecordMenus for a new Company.

    This function creates two default menus for non-energy companies:
    1. A system default menu "Todos Apontamentos" with highest order (99999)
    2. A regular menu "Apontamentos" with order 2
    And creates RecordMenuRelation between the "Apontamentos" RecordMenu and all active Users.

    Args:
        company (Company): The Company to create default menus for
    """

    if not is_energy_company(company):
        content_type = ContentType.objects.get(
            app_label="reportings", model="reporting"
        )
        active_users = User.objects.filter(uuid__in=company.get_active_users_id())

        # create default menu
        _ = RecordMenu.objects.create(
            name="Todos Apontamentos",
            content_type=content_type,
            order=99999,
            system_default=True,
            company=company,
            created_by=None,
        )
        menu = RecordMenu.objects.create(
            name="Apontamentos",
            content_type=content_type,
            order=2,
            system_default=False,
            company=company,
            created_by=None,
        )
        rm_relation_entries = []

        # Show menu for all users of the active Company
        for user in active_users:
            rm_relation_entries.extend(
                [
                    RecordMenuRelation(
                        record_menu=menu, user=user, order=1, company=company
                    ),
                ]
            )
        RecordMenuRelation.objects.bulk_create(rm_relation_entries)
