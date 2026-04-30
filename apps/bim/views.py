import os

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api.parsers import JSONParser as JSONAPIParser

from apps.reportings.models import Reporting

from .filters import BIMModelFilter
from .models import BIMModel
from .serializers import (
    BIMModelCreateSerializer,
    BIMModelSerializer,
    BIMModelStatusSerializer,
    BIMModelUploadSerializer,
)
from .utils import delete_bim_model_and_file

# Constantes de validação
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = [".ifc"]


class BIMModelViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet para gerenciamento de modelos BIM.

    Permissões são controladas pelo frontend através de:
    - metadata.canBimView: habilita/desabilita a aba BIM
    - customOptions.inventory.bim.allowedUsers: controla quem pode upload/delete
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BIMModelSerializer
    filterset_class = BIMModelFilter
    ordering = "-created_at"

    def get_parsers(self):
        """Retorna parsers apropriados para cada action."""
        # action pode não estar definido durante a inicialização
        action = getattr(self, "action", None)
        if action == "upload":
            return [MultiPartParser(), FormParser()]
        # Para create e outras actions, aceita JSON:API, JSON e multipart
        return [JSONAPIParser(), JSONParser(), MultiPartParser(), FormParser()]

    def get_serializer_class(self):
        """Usa serializer específico para criação com presigned URL."""
        if self.action == "create":
            return BIMModelCreateSerializer
        return BIMModelSerializer

    def get_queryset(self):
        """
        Retorna modelos BIM filtrados por inventory ou company.
        Usuário deve ter acesso à company para ver os modelos.
        """
        user_companies = self.request.user.companies.all()
        queryset = BIMModel.objects.filter(company__in=user_companies)

        # Filtrar por inventory se especificado
        inventory_id = self.request.query_params.get("inventory")
        if inventory_id:
            queryset = queryset.filter(inventory_id=inventory_id)

        # Filtrar por company se especificado
        company_id = self.request.query_params.get("company")
        if company_id:
            queryset = queryset.filter(company_id=company_id)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def destroy(self, request, *args, **kwargs):
        """
        Sobrescreve destroy para garantir deleção do arquivo no S3.

        DELETE /api/BIMModel/{uuid}/
        """
        instance = self.get_object()

        # Usar função helper para deletar modelo e arquivo S3
        success = delete_bim_model_and_file(instance)

        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                {"error": "Erro ao deletar modelo BIM"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["POST"], url_path="upload")
    def upload(self, request):
        """
        Inicia upload assíncrono de arquivo IFC.

        POST /api/BIMModel/upload/
        Body (multipart/form-data):
            - file: arquivo .ifc (max 100MB)
            - inventory_id: UUID do inventory relacionado
        """
        serializer = BIMModelUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data["file"]
        inventory_id = serializer.validated_data["inventory_id"]

        # Validação de extensão
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return Response(
                {
                    "error": f"Apenas arquivos {', '.join(ALLOWED_EXTENSIONS)} são aceitos"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validação de tamanho
        if file.size > MAX_FILE_SIZE:
            return Response(
                {
                    "error": f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE // (1024*1024)}MB"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Buscar inventory
        try:
            inventory = Reporting.objects.get(pk=inventory_id)
        except Reporting.DoesNotExist:
            return Response(
                {"error": "Inventory não encontrado"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Criar registro BIMModel
        bim_model = BIMModel.objects.create(
            company=inventory.company,
            created_by=request.user,
            inventory=inventory,
            name=file.name,
            file=file,
            file_size=file.size,
            status=BIMModel.STATUS_UPLOADING,
        )

        # Dispara task assíncrona
        from .asynchronous import process_bim_upload

        process_bim_upload(str(bim_model.uuid))

        return Response(
            {
                "uuid": str(bim_model.uuid),
                "status": bim_model.status,
                "name": bim_model.name,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["GET"], url_path="status")
    def status(self, request, pk=None):
        """
        Retorna status atual do processamento.

        GET /api/BIMModel/{uuid}/status/
        """
        bim_model = self.get_object()
        serializer = BIMModelStatusSerializer(bim_model)
        return Response(serializer.data)

    @action(detail=True, methods=["GET", "POST"], url_path="StartProcessing")
    def start_processing(self, request, pk=None):
        """
        Inicia o processamento do arquivo BIM após upload ao S3.

        GET/POST /api/BIMModel/{uuid}/StartProcessing/

        Este endpoint deve ser chamado pelo frontend APÓS o upload
        direto ao S3 ser concluído com sucesso.
        """
        bim_model = self.get_object()

        # Só inicia se estiver em status "uploading"
        if bim_model.status != BIMModel.STATUS_UPLOADING:
            return Response(
                {
                    "data": {
                        "status": "ALREADY_PROCESSING",
                        "message": f"Modelo já está em status: {bim_model.status}",
                    }
                }
            )

        # Dispara task assíncrona
        from .asynchronous import process_bim_upload

        process_bim_upload(str(bim_model.uuid))

        return Response(
            {
                "data": {
                    "status": "OK",
                    "message": "Processamento iniciado",
                    "uuid": str(bim_model.uuid),
                }
            }
        )
