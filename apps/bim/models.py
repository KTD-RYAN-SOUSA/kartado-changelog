import uuid

from django.contrib.gis.db import models
from simple_history.models import HistoricalRecords

from apps.companies.models import Company
from apps.reportings.models import Reporting
from apps.users.models import User
from RoadLabsAPI.storage_backends import PrivateMediaStorage


class BIMModel(models.Model):
    """Modelo para armazenar arquivos BIM/IFC vinculados a um Inventory."""

    # Status choices
    STATUS_UPLOADING = "uploading"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_UPLOADING, "Enviando"),
        (STATUS_PROCESSING, "Processando"),
        (STATUS_DONE, "Pronto"),
        (STATUS_ERROR, "Erro"),
    ]

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="bim_models",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="bim_models",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Relacionamento com Inventory (Reporting)
    inventory = models.ForeignKey(
        Reporting,
        on_delete=models.CASCADE,
        related_name="bim_models",
        help_text="Inventory ao qual este modelo BIM está vinculado",
    )

    # Arquivo
    name = models.CharField(max_length=255, help_text="Nome original do arquivo")
    file = models.FileField(
        storage=PrivateMediaStorage(),
        upload_to="bim/",
        blank=True,
        null=True,
    )
    file_size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Tamanho do arquivo em bytes",
    )

    # Status do processamento
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UPLOADING,
    )
    error_message = models.TextField(blank=True, default="")

    # Histórico
    history = HistoricalRecords(history_change_reason_field=models.TextField(null=True))

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Modelo BIM"
        verbose_name_plural = "Modelos BIM"

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def get_company_id(self):
        return self.company_id
