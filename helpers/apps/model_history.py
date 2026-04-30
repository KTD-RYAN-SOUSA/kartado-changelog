from rest_framework.response import Response


class History:
    def __init__(self, obj, obj_relations):
        """init

        Args:
            obj (DjangoModelObject): object to trace the history
            obj_relations (dic): object and its relations, containing its fields as values. Use "all" for all fields
        """

        self.contr_i_u_p = obj
        self.obj_relations = obj_relations
        self.response_data = {"data": []}

    def get_user(self, user):
        if user is not None:
            return user.uuid
        else:
            return None

    def get_history_type(self, history_type, q):
        history_types = {"-": "HistoryDeletion", "~": "HistoryChange"}

        if history_type == "+":
            return q.__class__.__name__ + "Created"
        else:
            return history_types[history_type]

    def generate_response_data(self):
        for q, v in self.obj_relations.items():
            deltas = []
            all_history = q.history.all().reverse()
            if len(all_history):
                rang = len(all_history) - 1
                first_history = all_history[0]
                self.response_data["data"].append(
                    {
                        "id": q.uuid,
                        "createdBy": self.get_user(first_history.history_user),
                        "createdAt": first_history.history_date,
                        "formData": {
                            "type": self.get_history_type(first_history.history_type, q)
                        },
                    }
                )
                for i in range(rang):
                    deltas.append(all_history[i + 1].diff_against(all_history[i]))
                for k, delta in enumerate(deltas):
                    changes = {"data": []}
                    for change in delta.changes:
                        if (change.field in v) or (v == "all"):
                            changes["data"].append(
                                {
                                    "fieldName": change.field,
                                    "oldValue": change.old,
                                    "newValue": change.new,
                                }
                            )
                        changes["type"] = self.get_history_type(
                            all_history[k + 1].history_type, q
                        )

                    if changes["data"]:
                        self.response_data["data"].append(
                            {
                                "id": q.uuid,
                                "createdBy": self.get_user(
                                    all_history[k + 1].history_user
                                ),
                                "createdAt": all_history[k + 1].history_date,
                                "formData": changes,
                            }
                        )
        return Response(data=self.response_data["data"], status=200)
