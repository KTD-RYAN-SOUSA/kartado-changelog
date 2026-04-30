import uuid

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("daily_reports", "0038_auto_20220209_1106"),
        ("companies", "0051_merge_20211207_0836"),
        ("service_orders", "0093_auto_20210601_1514"),
        ("resources", "0022_auto_20220207_1027"),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricalContractItemAdministration",
            fields=[
                (
                    "uuid",
                    models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
                ),
                ("sort_string", models.TextField()),
                (
                    "history_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("history_date", models.DateTimeField()),
                (
                    "history_change_reason",
                    models.CharField(max_length=100, null=True),
                ),
                (
                    "history_type",
                    models.CharField(
                        choices=[
                            ("+", "Created"),
                            ("~", "Changed"),
                            ("-", "Deleted"),
                        ],
                        max_length=1,
                    ),
                ),
                (
                    "board_item",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="daily_reports.DailyReportBoardItem",
                    ),
                ),
                (
                    "entity",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="companies.Entity",
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "resource",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="service_orders.ServiceOrderResource",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical contract item administration",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": "history_date",
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="ContractItemAdministration",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("sort_string", models.TextField()),
                (
                    "board_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="board_item_contract_administration_items",
                        to="daily_reports.DailyReportBoardItem",
                    ),
                ),
                (
                    "entity",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="entity_contract_administration_items",
                        to="companies.Entity",
                    ),
                ),
                (
                    "resource",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resource_contract_administration_items",
                        to="service_orders.ServiceOrderResource",
                    ),
                ),
            ],
        ),
    ]
