from apps.occurrence_records.models import OccurrenceRecord


def get_active_shape_file(occurrence_record: OccurrenceRecord) -> list:
    active_shape_file = list(
        map(
            str,
            list(occurrence_record.active_shape_files.values_list("pk", flat=True)),
        )
    )
    return active_shape_file


def get_default_config_map_to_report(occurrence_record: OccurrenceRecord) -> dict:
    """
    Gera um dicionário com as configurações padrão para o relatório de um registro de ocorrência.

    Esta função gera um dicionário que contém as configurações padrão para o relatório de um registro de ocorrência. As configurações incluem quais mapas devem ser incluídos no relatório, se os registros de ocorrência e propriedades devem ser incluídos, e qual arquivo de forma deve ser focado.

    Parâmetros:
    occurrence_record (OccurrenceRecord): O registro de ocorrência para o qual as configurações do relatório estão sendo geradas.

    Retorna:
    dict: Um dicionário contendo as configurações padrão para o relatório de um registro de ocorrência.
    """
    active_shape_file = get_active_shape_file(occurrence_record)

    return {
        "map_settings": [
            {
                "map": "default",
                "includes": {
                    "is_occurrence_record": True,
                    "is_properties": False,
                    "is_shape_file": True,
                    "active_shape_file": active_shape_file,
                },
                "focus": {"is_properties": False},
            },
            {
                "map": "satellite",
                "includes": {
                    "is_occurrence_record": True,
                    "is_properties": False,
                    "is_shape_file": True,
                    "active_shape_file": active_shape_file,
                },
                "focus": {"is_properties": True},
            },
            {
                "map": "default",
                "includes": {
                    "is_occurrence_record": True,
                    "is_properties": True,
                    "is_shape_file": True,
                    "active_shape_file": active_shape_file,
                },
                "focus": {"is_properties": False},
            },
            {
                "map": "satellite",
                "includes": {
                    "is_occurrence_record": True,
                    "is_properties": True,
                    "is_shape_file": True,
                    "active_shape_file": active_shape_file,
                },
                "focus": {"is_properties": False},
            },
        ],
    }
