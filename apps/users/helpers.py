from apps.companies.models import UserInCompany
from helpers.strings import to_camel_case


def get_uic_history(uic: UserInCompany) -> dict:
    """Returns UserInCompany history

    Args:
        uic (UserInCompany): UserInCompany instance for history extraction
    """

    def translate_active(value):
        return "Sim" if value else "Não"

    data = {}
    data["history"] = []

    # Writing this way to add base support for other fields in the future

    first_history = uic.history.filter(history_type="+")[0]
    first_values = [
        {"field": "isActive", "newValue": translate_active(first_history.is_active)}
    ]

    first_values = [
        {
            "field": item["field"],
            "action": "created",
            "oldValue": "",
            "newValue": item["newValue"],
        }
        for item in first_values
    ]
    data["history"].append(
        {
            "historyDate": first_history.history_date.replace(second=0, microsecond=0),
            "historyUser": str(first_history.history_user.uuid)
            if first_history.history_user
            else "",
            "historyChanges": first_values,
        }
    )

    remaining_histories = (
        uic.history.exclude(history_type="+")
        .prefetch_related("history_user", "user", "permissions", "company")
        .order_by("history_date")
    )

    for history in remaining_histories:
        previous_history = history.prev_record
        delta = history.diff_against(
            previous_history,
            excluded_fields=["uuid"],
        )
        new_history = {
            "historyDate": history.history_date.replace(second=0, microsecond=0),
            "historyUser": str(history.history_user.uuid)
            if history.history_user
            else "",
            "historyChanges": [],
        }
        for change in delta.changes:
            if change.field == "is_active":
                new_history["historyChanges"].append(
                    {
                        "field": to_camel_case(change.field),
                        "action": "updated",
                        "oldValue": translate_active(change.old),
                        "newValue": translate_active(change.new),
                    }
                )
        if new_history.get("historyChanges", []) != []:
            data["history"].append(new_history)
    data["history"].sort(
        key=lambda x: x["historyChanges"][0].get("field", ""), reverse=True
    )
    data["history"].sort(key=lambda x: x["historyDate"])

    return data
