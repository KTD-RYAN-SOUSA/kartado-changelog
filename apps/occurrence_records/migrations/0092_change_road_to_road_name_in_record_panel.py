import json

from django.db import migrations
from django_bulk_update.helper import bulk_update


def handle_record_panel_loop(app, schema_editor):
    # Obtém o modelo recordpanel
    RecordPanel = app.get_model("occurrence_records", "recordpanel")
    Road = app.get_model("roads", "road")

    def is_var_road(in_logic, key_name="road"):
        # Verifica se o dicionário contém a chave "var" e se o valor é igual a key_name
        return (
            isinstance(in_logic, dict)
            and "var" in in_logic
            and in_logic["var"] == key_name
        )

    def get_road_name(in_id):
        # Obtém o nome da estrada a partir do ID
        try:
            road_name = Road.objects.get(pk=in_id).name
        except Road.DoesNotExist:
            print(f"failed to get road_name for ID {in_id}")
            return in_id
        else:
            return road_name

    def recursively_rename_road_to_road_name(in_logic):
        # Função recursiva para renomear 'road' para 'road_name' e obter o nome da estrada
        if isinstance(in_logic, dict):
            for item in in_logic.values():
                recursively_rename_road_to_road_name(item)
        elif isinstance(in_logic, list):
            is_road_check = [is_var_road(a) for a in in_logic]
            if any(is_road_check):
                road_index = is_road_check.index(True)
                other_index = is_road_check.index(False)
                in_logic[road_index]["var"] = "road_name"
                if isinstance(in_logic[other_index], int):
                    in_logic[other_index] = get_road_name(in_logic[other_index])
                elif isinstance(in_logic[other_index], list):
                    in_logic[other_index] = [
                        get_road_name(a) for a in in_logic[other_index]
                    ]
            else:
                for item in in_logic:
                    recursively_rename_road_to_road_name(item)

    panels_to_update = []

    # Itera sobre todos os objetos RecordPanel
    for panel in RecordPanel.objects.all().only("uuid", "conditions"):
        # Verifica se conditions é um dicionário e se contém a chave 'logic'
        if isinstance(panel.conditions, dict) and "logic" in panel.conditions:
            logic = panel.conditions["logic"]
            # Verifica se 'road' está presente na lógica (como string JSON)
            if isinstance(logic, dict) and "road" in json.dumps(logic):
                # Renomeia 'road' para 'road_name' na lógica
                recursively_rename_road_to_road_name(logic)
                # Adiciona o painel à lista de atualização
                panels_to_update.append(panel)

    # Atualiza todos os paineis modificados em lote
    if panels_to_update:
        bulk_update(panels_to_update, batch_size=100, update_fields=["conditions"])


class Migration(migrations.Migration):

    dependencies = [
        ("occurrence_records", "0091_merge_20240422_1356"),
    ]

    operations = [
        migrations.RunPython(
            handle_record_panel_loop,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
