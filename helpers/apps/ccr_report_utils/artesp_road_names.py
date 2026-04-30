"""
Módulo para resolução de nomes completos de rodovias em relatórios ARTESP.

Este módulo fornece a função get_artesp_full_road_name() que consulta o
metadata da Company para obter o nome completo da rodovia baseado no
ID da rodovia e no km do apontamento.

Estrutura esperada no metadata da Company:
{
    "artesp_report_road_names": {
        "<road_id>": [
            {
                "km_begin": <float>,
                "km_end": <float>,
                "full_name": "<string>"
            }
        ]
    }
}
"""

from typing import TYPE_CHECKING

import sentry_sdk

if TYPE_CHECKING:
    from apps.companies.models import Company
    from apps.reportings.models import Reporting


def get_artesp_full_road_name(reporting: "Reporting", company: "Company") -> str:
    """
    Retorna o nome completo da rodovia para relatórios ARTESP.

    Consulta company.metadata["artesp_report_road_names"] para obter
    o nome completo baseado na rodovia e km do apontamento.

    Args:
        reporting: O apontamento com road e km
        company: A company com metadata contendo o mapeamento

    Returns:
        Nome completo da rodovia ou road_name original como fallback

    Note:
        Em caso de intervalos sobrepostos, o primeiro intervalo que
        corresponder ao km será utilizado.
    """
    fallback = reporting.road_name if reporting.road_name else ""

    if not reporting.road_id:
        return fallback

    if not company or not company.metadata:
        return fallback

    road_names_mapping = company.metadata.get("artesp_report_road_names")
    if not road_names_mapping:
        return fallback

    road_key = str(reporting.road_id)
    road_intervals = road_names_mapping.get(road_key)
    if not road_intervals or not isinstance(road_intervals, list):
        sentry_sdk.capture_message(
            f"Missing ARTESP road name configuration for road_id={road_key}, road_name='{reporting.road_name}'",
            "warning",
        )
        return fallback

    km = reporting.km
    if km is None:
        return fallback

    for interval in road_intervals:
        km_begin = interval.get("km_begin", 0)
        km_end = interval.get("km_end", float("inf"))
        if km_begin <= km <= km_end:
            return interval.get("full_name", fallback)

    sentry_sdk.capture_message(
        f"Missing ARTESP road name configuration for road_id={road_key}, road_name='{reporting.road_name}', km={km}",
        "warning",
    )
    return fallback
