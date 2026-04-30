"""
Helper functions for managing default road marks.

This module provides utilities to check and add default marks to roads
that don't have lot_logic configured.
"""

from zappa.asynchronous import task


@task
def async_recalculate_reporting_coordinates(reporting_ids, road_id):
    """
    Recalcula as coordenadas (point e geometry) dos apontamentos reassociados
    à rodovia real após a configuração do lot_logic.

    Executado de forma assíncrona via Zappa após o save da rodovia, garantindo
    que road.path e road.marks já estão atualizados no banco.

    Args:
        reporting_ids: Lista de IDs dos apontamentos a recalcular
        road_id: PK da rodovia real (string, pois Zappa serializa via JSON)
    """
    from django.contrib.gis.geos import GeometryCollection

    from apps.reportings.models import Reporting
    from apps.roads.models import Road
    from helpers.km_converter import check_valid_road, km_to_coordinates

    try:
        road = Road.objects.get(pk=road_id)
    except Road.DoesNotExist:
        return

    reportings = Reporting.objects.filter(pk__in=reporting_ids)
    to_update = []

    for reporting in reportings:
        try:
            if not check_valid_road(road, reporting.km):
                continue
            point, _ = km_to_coordinates(road, reporting.km)
            reporting.point = point
            reporting.geometry = GeometryCollection(point)
            to_update.append(reporting)
        except Exception:
            continue

    if to_update:
        Reporting.objects.bulk_update(to_update, ["point", "geometry"])


def has_default_marks(marks):
    """
    Verifica se já existem marcos padrão na estrutura de marks.

    Marcos padrão têm km -999999.0 ou 999999.0

    Args:
        marks (dict): Dicionário de marcos da rodovia

    Returns:
        bool: True se encontrar marcos padrão, False caso contrário
    """
    if not marks:
        return False

    for mark in marks.values():
        if isinstance(mark, dict) and "km" in mark:
            km = mark["km"]
            if km == -999999.0 or km == 999999.0:
                return True
    return False


def should_add_default_marks(road):
    """
    Verifica se deve adicionar marcos padrão à rodovia.

    Retorna True apenas se:
    1. Não tem lot_logic E
    2. Ainda não está marcada como is_default_segment E
    3. Não contém marcos padrão existentes

    Args:
        road: Instância do modelo Road

    Returns:
        bool: True se deve adicionar marcos padrão, False caso contrário
    """
    has_no_lot_logic = not road.lot_logic or road.lot_logic == {}
    already_has_default = road.is_default_segment or has_default_marks(road.marks)

    return has_no_lot_logic and not already_has_default


def reassociate_clone_reportings(road):
    """
    Quando uma road base recebe lot_logic, avalia os apontamentos vinculados
    aos seus clones (is_default_segment=True) e reassocia para a rodovia real
    aqueles cujo km está dentro do range válido da rodovia.

    Apontamentos com km fora do range permanecem vinculados ao clone.
    Os clones não são deletados.

    Args:
        road: Instância da road base que teve lot_logic adicionado
    """
    from apps.reportings.models import Reporting
    from apps.roads.models import Road
    from helpers.km_converter import check_valid_road

    if not road.id:
        return

    clones = Road.objects.filter(
        name=road.name,
        direction=road.direction,
        uf=road.uf or "",
        is_default_segment=True,
        company__in=road.company.all(),
    ).exclude(pk=road.pk)

    if not clones.exists():
        return

    reportings = Reporting.objects.filter(road__in=clones)

    valid_ids = [r.pk for r in reportings if check_valid_road(road, r.km)]

    if valid_ids:
        Reporting.objects.filter(pk__in=valid_ids).update(road=road)
        async_recalculate_reporting_coordinates(
            [str(v) for v in valid_ids], str(road.pk)
        )


def create_default_segment_road(original_road, company):
    """
    Cria ou retorna uma road clone com apenas marcos padrão.

    Verifica se já existe um clone da road base. Se existir, retorna o clone
    existente. Caso contrário, cria uma nova instância com os mesmos dados
    básicos mas apenas com marcos padrão que cobrem toda a extensão possível
    (km -999999 a 999999).

    Isso garante que existe apenas 1 clone por road base, evitando duplicação.

    Args:
        original_road: Road original que será clonada
        company: Company para vincular à nova road

    Returns:
        Road: Instância de road (existente ou nova) com marcos padrão e path calculado
    """
    from apps.roads.models import Road

    # Verifica se já existe um clone desta road.
    # Normaliza uf para "" pois CharField(blank=True) sem null=True
    # salva None como "" no banco, mas filter(uf=None) gera WHERE uf IS NULL
    # e não encontraria o clone existente.
    uf = original_road.uf or ""
    existing_clone = Road.objects.filter(
        name=original_road.name,
        direction=original_road.direction,
        uf=uf,
        is_default_segment=True,
        company=company,
    ).first()

    # Se já existe um clone, retorna ele
    if existing_clone:
        return existing_clone

    # Se não existe, cria novo clone
    # Define marcos padrão com coordenadas sem elevação (será adicionada pelo Router)
    default_marks = {
        "0": {
            "km": -999999.0,
            "point": {"type": "Point", "coordinates": [-47.0, -23.0]},
        },
        "1": {
            "km": 999999.0,
            "point": {"type": "Point", "coordinates": [-47.0001, -23.0001]},
        },
    }

    # Cria nova road com dados básicos clonados
    new_road = Road(
        name=original_road.name,
        description=f"Trecho padrão - {original_road.description or original_road.name}",
        direction=original_road.direction,
        marks=default_marks,
        uf=original_road.uf,
        lot_logic={},  # Sem lot_logic para trecho padrão
        lane_type_logic=original_road.lane_type_logic
        if hasattr(original_road, "lane_type_logic")
        else {},
        manual_road=True,  # Para não usar APIs externas
        is_default_segment=True,  # Marca como trecho padrão
        metadata=original_road.metadata if hasattr(original_road, "metadata") else {},
    )

    # Salva a road (dispara signal calculate_route que gera o path)
    new_road.save()

    # Vincula à company
    new_road.company.add(company)

    return new_road
