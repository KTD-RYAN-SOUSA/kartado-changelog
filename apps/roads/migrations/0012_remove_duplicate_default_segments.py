"""
Data migration - KTD-11056

Remove clones duplicados de rodovias com is_default_segment=True gerados pelo
bug KTD-11041.

O bug criava um novo clone Road(is_default_segment=True) a cada apontamento
criado fora do range de rodovias sem lot_logic, sem verificar se já existia um
clone para aquela combinação (name, direction, uf, company). Isso resultou em
múltiplos clones idênticos no banco.

Estratégia de limpeza:
  - Para cada company, agrupa clones por (name, direction, uf)
  - Mantém apenas o clone mais antigo (menor id) como canônico
  - Reassocia todos os Reporting.road dos clones extras para o canônico
  - Deleta os clones extras

A operação é irreversível (dados deletados não podem ser restaurados via
reverse migration). O reverse apenas emite um aviso.
"""

from django.db import migrations


def cleanup_duplicate_default_segments(apps, schema_editor):
    Road = apps.get_model("roads", "Road")
    Reporting = apps.get_model("reportings", "Reporting")
    Company = apps.get_model("companies", "Company")

    total_removed = 0
    total_reassociated = 0

    for company in Company.objects.all():
        # Busca todos os clones padrão associados a esta empresa
        default_clones = Road.objects.filter(
            is_default_segment=True,
            company=company,
        ).order_by("id")

        # Agrupa por (name, direction, uf)
        groups = {}
        for clone in default_clones:
            uf = clone.uf or ""
            key = (clone.name, clone.direction, uf)
            groups.setdefault(key, []).append(clone)

        for key, clones in groups.items():
            if len(clones) <= 1:
                continue

            # O mais antigo (menor id) é o canônico
            canonical = clones[0]
            duplicates = clones[1:]
            duplicate_ids = [d.id for d in duplicates]

            # Reassocia apontamentos dos clones extras para o canônico
            reassociated = Reporting.objects.filter(road_id__in=duplicate_ids).update(
                road=canonical
            )
            total_reassociated += reassociated

            # Remove os clones extras
            # Django limpa automaticamente as relações M2M (road.company)
            Road.objects.filter(id__in=duplicate_ids).delete()
            total_removed += len(duplicate_ids)

    print(
        f"\n[KTD-11056] Limpeza concluída: "
        f"{total_removed} clones removidos, "
        f"{total_reassociated} apontamentos reassociados."
    )


def reverse_cleanup(apps, schema_editor):
    # Operação irreversível — dados deletados não podem ser restaurados
    print(
        "\n[KTD-11056] AVISO: Esta migration é irreversível. "
        "Os clones duplicados removidos não podem ser restaurados via reverse."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("roads", "0011_auto_20260402_1026"),
        ("reportings", "0066_reporting_inventory_candidates"),
        ("companies", "0075_merge_0074_auto_20250604_1735_0074_auto_20250909_1951"),
    ]

    operations = [
        migrations.RunPython(
            cleanup_duplicate_default_segments,
            reverse_code=reverse_cleanup,
        ),
    ]
