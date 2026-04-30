import pytest
from rest_framework import status

from apps.reportings.models import RecordMenuRelation
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestRecordMenuRelation(TestBase):
    model = "RecordMenu"

    def get_visible_relations(self):
        relations = RecordMenuRelation.objects.filter(
            hide_menu=False,
            company=self.company,
            user=self.user,
            record_menu__system_default=False,
        ).order_by("order")
        assert relations.count() > 1

        return relations

    def test_move_down_endpoint(self, client):
        relations = self.get_visible_relations()

        top_menu_relation = relations[0]
        top_menu = top_menu_relation.record_menu
        second_menu_relation = relations[1]

        response = client.patch(
            path="/RecordMenu/{}/MoveDown/".format(str(top_menu.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {}},
        )

        new_top_menu_relation = RecordMenuRelation.objects.get(
            pk=second_menu_relation.pk
        )
        new_second_menu_relation = RecordMenuRelation.objects.get(
            pk=top_menu_relation.pk
        )

        assert response.status_code == status.HTTP_200_OK
        assert top_menu_relation.order == new_top_menu_relation.order
        assert second_menu_relation.order == new_second_menu_relation.order

    def test_move_up_endpoint(self, client):
        relations = self.get_visible_relations()

        top_menu_relation = relations[0]
        second_menu_relation = relations[1]
        second_menu = second_menu_relation.record_menu

        response = client.patch(
            path="/RecordMenu/{}/MoveUp/".format(str(second_menu.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={"data": {}},
        )

        new_top_menu_relation = RecordMenuRelation.objects.get(
            pk=second_menu_relation.pk
        )
        new_second_menu_relation = RecordMenuRelation.objects.get(
            pk=top_menu_relation.pk
        )

        assert response.status_code == status.HTTP_200_OK
        assert top_menu_relation.order == new_top_menu_relation.order
        assert second_menu_relation.order == new_second_menu_relation.order

    def test_relations_have_ascending_order(self, client):
        """The visible menus for the user should always start from zero and increase one by one"""

        relations = self.get_visible_relations()
        ideal_orders = list(range(relations.count()))
        current_orders = list(relations.values_list("order", flat=True))

        assert ideal_orders == current_orders
