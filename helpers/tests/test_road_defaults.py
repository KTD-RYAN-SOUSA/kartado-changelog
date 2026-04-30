"""
Testes para helpers/road_defaults.py

Cobre o bug KTD-11041: duplicação de segmento padrão (is_default_segment)
ao criar múltiplos apontamentos fora dos limites de uma rodovia sem lot_logic.
"""

from unittest.mock import MagicMock, patch

import pytest

from helpers.road_defaults import (
    create_default_segment_road,
    has_default_marks,
    reassociate_clone_reportings,
    should_add_default_marks,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MARKS_NORMAL = {
    "0": {"km": 0.0, "point": {"type": "Point", "coordinates": [-49.0, -23.0]}},
    "1": {"km": 10.0, "point": {"type": "Point", "coordinates": [-49.1, -23.1]}},
}

MARKS_WITH_DEFAULT = {
    "0": {"km": -999999.0, "point": {"type": "Point", "coordinates": [-47.0, -23.0]}},
    "1": {
        "km": 999999.0,
        "point": {"type": "Point", "coordinates": [-47.0001, -23.0001]},
    },
}


def make_router_mock(marks=None):
    router = MagicMock()
    router.path = None
    router.length = 100.0
    router.dict_mark = marks or MARKS_NORMAL
    return router


@pytest.fixture
def company():
    from apps.companies.models import Company

    return Company.objects.first()


@pytest.fixture
def road_factory(company):
    from apps.roads.models import Road

    created = []

    def factory(
        name="TestRoad",
        lot_logic=None,
        uf="SP",
        is_default_segment=False,
        marks=None,
        **kwargs
    ):
        router = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                road = Road.objects.create(
                    name=name,
                    direction=1,
                    marks=marks if marks is not None else MARKS_NORMAL,
                    lot_logic=lot_logic or {},
                    uf=uf,
                    is_default_segment=is_default_segment,
                    **kwargs,
                )
                road.company.add(company)
                created.append(road)
        return road

    yield factory

    Road.objects.filter(pk__in=[r.pk for r in created]).delete()


# ---------------------------------------------------------------------------
# has_default_marks
# ---------------------------------------------------------------------------


class TestHasDefaultMarks:
    def test_retorna_false_para_marks_vazias(self):
        assert has_default_marks({}) is False
        assert has_default_marks(None) is False

    def test_retorna_false_para_marks_normais(self):
        assert has_default_marks(MARKS_NORMAL) is False

    def test_retorna_true_para_km_negativo_extremo(self):
        marks = {"0": {"km": -999999.0, "point": {}}}
        assert has_default_marks(marks) is True

    def test_retorna_true_para_km_positivo_extremo(self):
        marks = {"0": {"km": 999999.0, "point": {}}}
        assert has_default_marks(marks) is True

    def test_retorna_false_para_mark_sem_km(self):
        marks = {"0": {"point": {}}}
        assert has_default_marks(marks) is False


# ---------------------------------------------------------------------------
# should_add_default_marks
# ---------------------------------------------------------------------------


class TestShouldAddDefaultMarks:
    def test_retorna_true_para_road_sem_lot_logic_e_sem_default(self, road_factory):
        road = road_factory(lot_logic={})
        assert should_add_default_marks(road) is True

    def test_retorna_false_se_road_ja_e_default_segment(self, road_factory):
        road = road_factory(is_default_segment=True)
        assert should_add_default_marks(road) is False

    def test_retorna_false_se_road_tem_lot_logic(self, road_factory):
        road = road_factory(lot_logic={"segment": "A"})
        assert should_add_default_marks(road) is False

    def test_retorna_false_se_marks_ja_tem_valores_extremos(self, road_factory):
        router = make_router_mock(marks=MARKS_WITH_DEFAULT)
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                from apps.roads.models import Road

                road = Road.objects.create(
                    name="DefaultMarksRoad",
                    direction=1,
                    marks=MARKS_WITH_DEFAULT,
                    lot_logic={},
                )
        assert should_add_default_marks(road) is False


# ---------------------------------------------------------------------------
# create_default_segment_road — BUG KTD-11041
# ---------------------------------------------------------------------------


class TestCreateDefaultSegmentRoad:
    def test_cria_clone_quando_nao_existe(self, road_factory, company):
        """Deve criar um novo clone com is_default_segment=True."""
        from apps.roads.models import Road

        road = road_factory(name="RoadSemClone", uf="SP")

        router = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                clone = create_default_segment_road(road, company)

        assert clone.is_default_segment is True
        assert clone.name == road.name
        assert Road.objects.filter(name=road.name, is_default_segment=True).count() == 1

    def test_reutiliza_clone_existente_sem_duplicar(self, road_factory, company):
        """
        Regressão KTD-11041: segunda chamada deve retornar o clone existente,
        não criar um novo.
        """
        from apps.roads.models import Road

        road = road_factory(name="RoadDuplicacao", uf="SP")

        router = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                clone1 = create_default_segment_road(road, company)
                clone2 = create_default_segment_road(road, company)

        assert clone1.pk == clone2.pk, "Deve reutilizar o clone, não criar novo"
        assert Road.objects.filter(name=road.name, is_default_segment=True).count() == 1

    def test_reutiliza_clone_quando_uf_e_none(self, road_factory, company):
        """
        Regressão KTD-11041: roads com uf=None (legado) não devem gerar
        duplicatas. CharField sem null=True salva '' no banco, então
        filter(uf=None) gerava WHERE uf IS NULL e não encontrava o clone.
        """
        from apps.roads.models import Road

        road = road_factory(name="RoadUfNone", uf="")

        router = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                clone1 = create_default_segment_road(road, company)

                # Simula uf=None no objeto Python (antes de salvar)
                road.uf = None

                clone2 = create_default_segment_road(road, company)

        assert clone1.pk == clone2.pk, "uf=None deve ser normalizado para '' na busca"
        assert Road.objects.filter(name=road.name, is_default_segment=True).count() == 1

    def test_clone_herda_name_direction_uf(self, road_factory, company):
        """O clone deve herdar os campos básicos da road original."""
        road = road_factory(name="RoadHeranca", uf="RJ")

        router = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                clone = create_default_segment_road(road, company)

        assert clone.name == road.name
        assert clone.direction == road.direction
        assert clone.uf == road.uf
        assert clone.lot_logic == {}

    def test_clone_tem_marks_com_km_extremos(self, road_factory, company):
        """O clone deve ter marcos com km -999999 e 999999.

        O signal calculate_route sobrescreve os marks com o retorno do Router,
        então o mock deve retornar os marks padrão para o clone.
        """
        road = road_factory(name="RoadMarksExtremos", uf="MG")

        router = make_router_mock(marks=MARKS_WITH_DEFAULT)
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                clone = create_default_segment_road(road, company)

        assert has_default_marks(clone.marks) is True


# ---------------------------------------------------------------------------
# reassociate_clone_reportings
# ---------------------------------------------------------------------------


class TestReassociateCloneReportings:
    def test_nao_faz_nada_para_road_sem_id(self):
        """Não deve crashar se a road ainda não foi salva."""
        from apps.roads.models import Road

        road = Road(name="Sem ID", direction=1, marks=MARKS_NORMAL)
        reassociate_clone_reportings(road)  # não deve lançar exceção

    def test_nao_faz_nada_sem_clones(self, road_factory):
        """Não deve fazer nada se não há clones."""
        road = road_factory(name="RoadSemClone", lot_logic={"segment": "A"}, uf="SP")
        reassociate_clone_reportings(road)  # não deve lançar exceção

    def test_clone_nao_e_deletado(self, road_factory, company):
        """Clone deve ser mantido mesmo após a reassociação."""
        from apps.roads.models import Road

        road = road_factory(name="RoadMantemClone", uf="SP")

        router = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                create_default_segment_road(road, company)

        assert Road.objects.filter(name=road.name, is_default_segment=True).count() == 1

        reassociate_clone_reportings(road)

        assert (
            Road.objects.filter(name=road.name, is_default_segment=True).count() == 1
        ), "Clone não deve ser deletado"

    def test_road_base_nao_e_afetada(self, road_factory, company):
        """A road base (is_default_segment=False) não deve ser alterada."""
        from apps.roads.models import Road

        road = road_factory(name="RoadBase", uf="SP")

        router = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                create_default_segment_road(road, company)

        reassociate_clone_reportings(road)

        assert Road.objects.filter(
            pk=road.pk
        ).exists(), "Road base não deve ser afetada"

    def test_reassocia_apontamento_com_km_valido(self, road_factory, company):
        """Apontamento com km dentro do range deve ser reassociado à rodovia real."""
        from apps.reportings.models import Reporting

        road = road_factory(name="RoadReassoc", uf="SP", marks=MARKS_NORMAL)

        router = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                clone = create_default_segment_road(road, company)

        reporting = Reporting.objects.filter(company=company).first()
        if reporting is None:
            pytest.skip("Nenhum Reporting disponível para o teste")

        original_road = reporting.road_id
        original_km = reporting.km
        Reporting.objects.filter(pk=reporting.pk).update(
            road=clone, km=5.0
        )  # dentro do range (0–10)

        reassociate_clone_reportings(road)

        reporting.refresh_from_db()
        assert (
            reporting.road_id == road.pk
        ), "Reporting deve ser reassociado à rodovia real"

        Reporting.objects.filter(pk=reporting.pk).update(
            road=original_road, km=original_km
        )

    def test_mantem_apontamento_com_km_invalido_no_clone(self, road_factory, company):
        """Apontamento com km fora do range deve permanecer vinculado ao clone."""
        from apps.reportings.models import Reporting

        road = road_factory(name="RoadKmInvalido", uf="SP", marks=MARKS_NORMAL)

        router = make_router_mock()
        with patch("apps.roads.signals.Router", return_value=router):
            with patch("apps.roads.signals.reassociate_clone_reportings"):
                clone = create_default_segment_road(road, company)

        reporting = Reporting.objects.filter(company=company).first()
        if reporting is None:
            pytest.skip("Nenhum Reporting disponível para o teste")

        original_road = reporting.road_id
        original_km = reporting.km
        Reporting.objects.filter(pk=reporting.pk).update(
            road=clone, km=999.0
        )  # fora do range

        reassociate_clone_reportings(road)

        reporting.refresh_from_db()
        assert (
            reporting.road_id == clone.pk
        ), "Reporting com km inválido deve permanecer no clone"

        Reporting.objects.filter(pk=reporting.pk).update(
            road=original_road, km=original_km
        )
