from unittest.mock import MagicMock, patch

import pytest
from django.db.models.signals import m2m_changed

from apps.companies.models import Company
from apps.roads.models import Road

pytestmark = pytest.mark.django_db


MOCK_LENGTH = 100.0
MARKS_WITH_INDEXES = {
    "0": {
        "km": 0.0,
        "index": 0,
        "point": {"type": "Point", "coordinates": [-49.0, -23.0]},
    },
    "1": {
        "km": 1.0,
        "index": 1,
        "point": {"type": "Point", "coordinates": [-49.1, -23.1]},
    },
}
MARKS_WITHOUT_INDEXES = {
    "0": {"km": 0.0, "point": {"type": "Point", "coordinates": [-49.0, -23.0]}},
    "1": {"km": 1.0, "point": {"type": "Point", "coordinates": [-49.1, -23.1]}},
}


def make_router_mock(dict_mark=None):
    router_instance = MagicMock()
    router_instance.path = None
    router_instance.length = MOCK_LENGTH
    router_instance.dict_mark = (
        dict_mark if dict_mark is not None else MARKS_WITH_INDEXES
    )
    return router_instance


@pytest.fixture
def company():
    return Company.objects.first()


@pytest.fixture
def road_factory(company):
    created = []

    def factory(name="TestRoad", lot_logic=None, marks=None, **kwargs):
        if marks is None:
            marks = MARKS_WITH_INDEXES
        if lot_logic is None:
            lot_logic = {}

        router_instance = make_router_mock(dict_mark=marks)

        with patch("apps.roads.signals.Router", return_value=router_instance):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                road = Road.objects.create(
                    name=name,
                    direction=1,
                    marks=marks,
                    lot_logic=lot_logic,
                    **kwargs,
                )
                road.company.add(company)
                created.append(road)

        return road

    yield factory

    Road.objects.filter(pk__in=[r.pk for r in created]).delete()


class TestCalculateRoute:
    def test_calculate_route_sets_path_and_length(self, company):
        router_instance = make_router_mock()

        with patch("apps.roads.signals.Router", return_value=router_instance):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                road = Road.objects.create(
                    name="RouteRoad",
                    direction=1,
                    marks=MARKS_WITH_INDEXES,
                )
                road.company.add(company)

        road.refresh_from_db()
        assert road.path is None
        assert road.length == MOCK_LENGTH

    def test_calculate_route_with_lot_logic_reassociates_clones(self, company):
        router_instance = make_router_mock()

        with patch("apps.roads.signals.Router", return_value=router_instance):
            with patch(
                "apps.roads.signals.reassociate_clone_reportings"
            ) as mock_reassociate:
                Road.objects.create(
                    name="LotLogicRoad",
                    direction=1,
                    marks=MARKS_WITH_INDEXES,
                    lot_logic={"segment": "A"},
                )

        mock_reassociate.assert_called()

    def test_calculate_route_without_lot_logic_no_delete(self, company):
        router_instance = make_router_mock()

        with patch("apps.roads.signals.Router", return_value=router_instance):
            with patch(
                "apps.roads.signals.reassociate_clone_reportings"
            ) as mock_delete:
                Road.objects.create(
                    name="NoLotLogicRoad",
                    direction=1,
                    marks=MARKS_WITH_INDEXES,
                    lot_logic={},
                )

        mock_delete.assert_not_called()

    def test_calculate_route_sets_all_marks_have_indexes_true(self, company):
        router_instance = make_router_mock(dict_mark=MARKS_WITH_INDEXES)

        with patch("apps.roads.signals.Router", return_value=router_instance):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                road = Road.objects.create(
                    name="AllIndexesRoad",
                    direction=1,
                    marks=MARKS_WITH_INDEXES,
                )
                road.company.add(company)

        road.refresh_from_db()
        assert road.all_marks_have_indexes is True

    def test_calculate_route_sets_all_marks_have_indexes_false(self, company):
        router_instance = make_router_mock(dict_mark=MARKS_WITHOUT_INDEXES)

        with patch("apps.roads.signals.Router", return_value=router_instance):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                road = Road.objects.create(
                    name="MissingIndexRoad",
                    direction=1,
                    marks=MARKS_WITHOUT_INDEXES,
                )
                road.company.add(company)

        road.refresh_from_db()
        assert road.all_marks_have_indexes is False


class TestUpdateLotLogicInRoads:
    def test_propagates_lot_logic_to_roads_with_same_name(self, road_factory, company):
        lot_logic_value = {"segment": "X"}
        road_a = road_factory(name="SharedName", lot_logic=lot_logic_value)
        road_b = road_factory(name="SharedName", lot_logic={})

        road_a.created_flag = False

        m2m_changed.send(
            sender=Road.company.through,
            instance=road_a,
            action="post_add",
        )

        road_b.refresh_from_db()
        assert road_b.lot_logic == lot_logic_value

    def test_no_propagation_on_other_actions(self, road_factory, company):
        lot_logic_value = {"segment": "Y"}
        road_a = road_factory(name="ActionRoad", lot_logic=lot_logic_value)
        road_b = road_factory(name="ActionRoad", lot_logic={})

        Road.objects.filter(pk=road_b.pk).update(lot_logic={})

        m2m_changed.send(
            sender=Road.company.through,
            instance=road_a,
            action="post_remove",
        )

        road_b.refresh_from_db()
        assert road_b.lot_logic == {}

    def test_inherits_lot_logic_when_own_is_empty_and_created(
        self, road_factory, company
    ):
        lot_logic_value = {"segment": "Z"}
        road_factory(name="InheritRoad", lot_logic=lot_logic_value)
        road_new = road_factory(name="InheritRoad", lot_logic={})

        road_new.created_flag = True

        m2m_changed.send(
            sender=Road.company.through,
            instance=road_new,
            action="post_add",
        )

        road_new.refresh_from_db()
        assert road_new.lot_logic == lot_logic_value

    def test_no_inherit_when_not_created(self, road_factory, company):
        lot_logic_value = {"segment": "W"}
        road_factory(name="NoInheritRoad", lot_logic=lot_logic_value)
        road_update = road_factory(name="NoInheritRoad", lot_logic={})

        Road.objects.filter(pk=road_update.pk).update(lot_logic={})
        road_update.refresh_from_db()
        road_update.created_flag = False

        m2m_changed.send(
            sender=Road.company.through,
            instance=road_update,
            action="post_add",
        )

        road_update.refresh_from_db()
        assert road_update.lot_logic == {}


class TestUpdateLotLogicOnUpdate:
    def test_propagates_lot_logic_on_update(self, road_factory, company):
        lot_logic_value = {"segment": "U"}
        road_a = road_factory(name="UpdateRoad", lot_logic=lot_logic_value)
        road_b = road_factory(name="UpdateRoad", lot_logic={})

        router_instance = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router_instance):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                road_a.save()

        road_b.refresh_from_db()
        assert road_b.lot_logic == lot_logic_value

    def test_no_propagation_on_create(self, company):
        router_instance = make_router_mock()
        road_b_initial_lot_logic = {"segment": "existing"}
        road_b = None

        with patch("apps.roads.signals.Router", return_value=router_instance):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                road_b = Road.objects.create(
                    name="CreateNoPropRoad",
                    direction=1,
                    marks=MARKS_WITH_INDEXES,
                    lot_logic=road_b_initial_lot_logic,
                )
                road_b.company.add(company)

                Road.objects.create(
                    name="CreateNoPropRoad",
                    direction=1,
                    marks=MARKS_WITH_INDEXES,
                    lot_logic={},
                )

        road_b.refresh_from_db()
        assert road_b.lot_logic == road_b_initial_lot_logic

        Road.objects.filter(name="CreateNoPropRoad").delete()

    def test_no_propagation_when_lot_logic_empty(self, road_factory, company):
        lot_logic_value = {"segment": "V"}
        road_a = road_factory(name="EmptyLotRoad", lot_logic={})
        road_b = road_factory(name="EmptyLotRoad", lot_logic=lot_logic_value)

        router_instance = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router_instance):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                road_a.save()

        road_b.refresh_from_db()
        assert road_b.lot_logic == lot_logic_value
