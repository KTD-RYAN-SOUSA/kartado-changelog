FIELD_NAMES = {
    "datetime": "Data e horário",
    "number": "Número",
    "company": "Companhia",
    "occurrence_kind": "Tipo de ocorrência",
    "uf_code": "Código UF",
    "city": "Cidade",
    "place_on_dam": "Local na barragem",
    "river": "Rio",
    "point": "Coordenadas",
    "distance_from_dam": "Distância da barragem",
    "origin": "Origem",
    "origin_media": "Meio de origem",
    "informer": "Informante",
    "created_by": "Criador",
    "occurrence_type": "Tipo de ocorrência",
    "form_data": "Formulário",
}


def get_readable_field_name(field_name):
    return FIELD_NAMES.get(field_name, field_name)
