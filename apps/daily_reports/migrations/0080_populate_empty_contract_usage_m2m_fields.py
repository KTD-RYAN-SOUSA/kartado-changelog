# Generated manually on 2026-02-10

from django.db import connection, migrations
from tqdm import tqdm


def populate_empty_m2m_fields(apps, schema_editor):
    """
    Populate empty M2M fields (daily_reports and multiple_daily_reports) in
    DailyReportContractUsage from related Worker/Equipment/Vehicle instances.

    This migration only processes ContractUsages where M2M fields are empty,
    making it safe to run after migration 0079.
    """
    db_alias = schema_editor.connection.alias
    DailyReportContractUsage = apps.get_model(
        "daily_reports", "DailyReportContractUsage"
    )

    # Get IDs of ContractUsages that already have M2M relations
    # Using raw SQL to check the through tables directly
    with connection.cursor() as cursor:
        # Get ContractUsages that have daily_reports
        cursor.execute(
            """
            SELECT DISTINCT dailyreportcontractusage_id
            FROM daily_reports_dailyreportcontractusage_daily_reports
            """
        )
        contract_usages_with_daily_reports = {row[0] for row in cursor.fetchall()}

        # Get ContractUsages that have multiple_daily_reports
        cursor.execute(
            """
            SELECT DISTINCT dailyreportcontractusage_id
            FROM daily_reports_dailyreportcontractusage_multiple_daily_reports
            """
        )
        contract_usages_with_multiple_daily_reports = {
            row[0] for row in cursor.fetchall()
        }

    # ContractUsages that have AT LEAST ONE M2M populated (we skip these)
    # Using union (|) to get all that have daily_reports OR multiple_daily_reports
    contract_usages_with_any_m2m = (
        contract_usages_with_daily_reports | contract_usages_with_multiple_daily_reports
    )

    print(
        f"\nContractUsages com daily_reports: {len(contract_usages_with_daily_reports)}"
    )
    print(
        f"ContractUsages com multiple_daily_reports: {len(contract_usages_with_multiple_daily_reports)}"
    )
    print(
        f"ContractUsages com pelo menos 1 M2M populado: {len(contract_usages_with_any_m2m)}"
    )

    # Filter: exclude ContractUsages that have AT LEAST ONE M2M populated
    # Only process ContractUsages with NO M2M relations at all
    contract_usages_qs = (
        DailyReportContractUsage.objects.using(db_alias)
        .exclude(uuid__in=contract_usages_with_any_m2m)
        .prefetch_related(
            # Worker e seus relacionamentos M2M
            "worker",
            "worker__daily_reports",
            "worker__multiple_daily_reports",
            # Equipment e seus relacionamentos M2M
            "equipment",
            "equipment__daily_reports",
            "equipment__multiple_daily_reports",
            # Vehicle e seus relacionamentos M2M
            "vehicle",
            "vehicle__daily_reports",
            "vehicle__multiple_daily_reports",
            # M2M do próprio ContractUsage (para verificar se está vazio)
            "daily_reports",
            "multiple_daily_reports",
        )
    )

    total_count = contract_usages_qs.count()
    print(f"\nTotal de ContractUsages sem nenhuma relação M2M: {total_count}")

    if total_count == 0:
        print(
            "Todos os ContractUsages já têm pelo menos 1 relação M2M. Migration concluída!"
        )
        return

    m2m_updates = []
    processed_count = 0
    skipped_count = 0

    # Processar em batches usando iterator
    for contract_usage in tqdm(
        contract_usages_qs.iterator(chunk_size=2000),
        desc="Processando ContractUsages",
        total=total_count,
    ):
        # Verificar se M2M já está populado
        has_daily_reports = contract_usage.daily_reports.exists()
        has_multiple_daily_reports = contract_usage.multiple_daily_reports.exists()

        # Se ambos já estão populados, pular
        if has_daily_reports and has_multiple_daily_reports:
            skipped_count += 1
            continue

        resource = None
        daily_reports_ids = []
        multiple_daily_reports_ids = []

        # Identificar qual resource está vinculado
        if contract_usage.worker:
            resource = contract_usage.worker
        elif contract_usage.equipment:
            resource = contract_usage.equipment
        elif contract_usage.vehicle:
            resource = contract_usage.vehicle

        # Obter IDs dos M2M do resource (já prefetchados)
        if resource:
            # Só buscar daily_reports se estiver vazio
            if not has_daily_reports:
                daily_reports_ids = [dr.uuid for dr in resource.daily_reports.all()]

            # Só buscar multiple_daily_reports se estiver vazio
            if not has_multiple_daily_reports:
                multiple_daily_reports_ids = [
                    mdr.uuid for mdr in resource.multiple_daily_reports.all()
                ]

            # Guardar para atualizar M2M depois (só se tiver algum ID para atualizar)
            if daily_reports_ids or multiple_daily_reports_ids:
                m2m_updates.append(
                    (
                        contract_usage.uuid,
                        daily_reports_ids,
                        multiple_daily_reports_ids,
                        has_daily_reports,
                        has_multiple_daily_reports,
                    )
                )

        processed_count += 1

    print(f"\nContractUsages processados: {processed_count}")
    print(f"ContractUsages pulados (já populados): {skipped_count}")
    print(f"ContractUsages com M2M para atualizar: {len(m2m_updates)}")

    # Atualizar M2M em batches
    if m2m_updates:
        batch_m2m = []
        for (
            uuid,
            daily_reports_ids,
            multiple_daily_reports_ids,
            has_daily_reports,
            has_multiple_daily_reports,
        ) in tqdm(m2m_updates, desc="Atualizando M2M"):
            batch_m2m.append(
                (
                    uuid,
                    daily_reports_ids,
                    multiple_daily_reports_ids,
                    has_daily_reports,
                    has_multiple_daily_reports,
                )
            )

            # Processar M2M a cada 2000 registros para liberar memória
            if len(batch_m2m) >= 2000:
                for (
                    m2m_uuid,
                    m2m_daily_reports_ids,
                    m2m_multiple_daily_reports_ids,
                    m2m_has_daily_reports,
                    m2m_has_multiple_daily_reports,
                ) in batch_m2m:
                    contract_usage = DailyReportContractUsage.objects.using(
                        db_alias
                    ).get(uuid=m2m_uuid)

                    # Só atualizar daily_reports se estava vazio e tem IDs para adicionar
                    if not m2m_has_daily_reports and m2m_daily_reports_ids:
                        contract_usage.daily_reports.set(m2m_daily_reports_ids)

                    # Só atualizar multiple_daily_reports se estava vazio e tem IDs para adicionar
                    if (
                        not m2m_has_multiple_daily_reports
                        and m2m_multiple_daily_reports_ids
                    ):
                        contract_usage.multiple_daily_reports.set(
                            m2m_multiple_daily_reports_ids
                        )

                batch_m2m = []  # Limpar batch

        # Processar M2M restantes
        if batch_m2m:
            for (
                m2m_uuid,
                m2m_daily_reports_ids,
                m2m_multiple_daily_reports_ids,
                m2m_has_daily_reports,
                m2m_has_multiple_daily_reports,
            ) in batch_m2m:
                contract_usage = DailyReportContractUsage.objects.using(db_alias).get(
                    uuid=m2m_uuid
                )

                # Só atualizar daily_reports se estava vazio e tem IDs para adicionar
                if not m2m_has_daily_reports and m2m_daily_reports_ids:
                    contract_usage.daily_reports.set(m2m_daily_reports_ids)

                # Só atualizar multiple_daily_reports se estava vazio e tem IDs para adicionar
                if (
                    not m2m_has_multiple_daily_reports
                    and m2m_multiple_daily_reports_ids
                ):
                    contract_usage.multiple_daily_reports.set(
                        m2m_multiple_daily_reports_ids
                    )

    print("\nMigração concluída com sucesso!")


def reverse_populate_empty_m2m_fields(apps, schema_editor):
    """
    Reverse migration: clear M2M fields that were populated by this migration.
    Note: This will clear ALL M2M fields, not just the ones we populated.
    """
    db_alias = schema_editor.connection.alias
    DailyReportContractUsage = apps.get_model(
        "daily_reports", "DailyReportContractUsage"
    )

    contract_usages_qs = DailyReportContractUsage.objects.using(db_alias).all()
    total_count = contract_usages_qs.count()

    # Limpar M2M em batches
    for contract_usage in tqdm(
        contract_usages_qs.iterator(chunk_size=2000),
        desc="Limpando M2M",
        total=total_count,
    ):
        contract_usage.daily_reports.clear()
        contract_usage.multiple_daily_reports.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("daily_reports", "0079_populate_contract_usage_denormalized_fields"),
    ]

    operations = [
        migrations.RunPython(
            populate_empty_m2m_fields,
            reverse_code=reverse_populate_empty_m2m_fields,
        ),
    ]
