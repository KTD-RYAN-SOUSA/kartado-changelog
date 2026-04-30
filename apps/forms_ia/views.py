import logging
import uuid

import requests
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from helpers.aws import get_forms_ia_credentials
from helpers.permissions import PermissionManager, join_queryset
from RoadLabsAPI.settings import credentials

from .models import FormsIARequest
from .permissions import FormsIARequestPermissions
from .serializers import FormsIARequestCreateSerializer, FormsIARequestSerializer

logger = logging.getLogger(__name__)


class FormsIARequestView(viewsets.ModelViewSet):
    """
    ViewSet for Forms IA requests
    """

    permission_classes = [IsAuthenticated, FormsIARequestPermissions]
    permissions = None
    ordering = "uuid"

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return FormsIARequest.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="FormsIARequest",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, FormsIARequest.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    FormsIARequest.objects.filter(
                        company_id=user_company, created_by=self.request.user
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, FormsIARequest.objects.filter(company_id=user_company)
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = FormsIARequest.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def get_serializer_class(self):
        if self.action == "create":
            return FormsIARequestCreateSerializer
        return FormsIARequestSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if not instance.done and not instance.error and instance.request_id:
            stage = credentials.stage.upper()
            api_credentials = get_forms_ia_credentials(stage)

            try:
                headers = {"x-api-key": api_credentials["api_key"]}
                get_url = f"{api_credentials['api_url']}?id={instance.request_id}"
                bedrock_response = requests.get(
                    get_url,
                    headers=headers,
                    timeout=30,
                )

                if bedrock_response.status_code != 200:
                    raise Exception(
                        f"Bedrock API error: {bedrock_response.status_code} - {bedrock_response.text}"
                    )

                bedrock_data = bedrock_response.json()
                status_value = bedrock_data.get("status")

                if status_value == "COMPLETED":
                    result = bedrock_data.get("result", {})
                    instance.output_json = {"data": result.get("response", {})}
                    instance.done = True
                    instance.save()
                elif status_value == "FAILED":
                    instance.error = True
                    instance.error_message = bedrock_data.get(
                        "error_message", "Falha no processamento"
                    )
                    instance.save()
            except Exception as e:
                logger.error(f"Error checking Bedrock status: {str(e)}")
                instance.error = True
                instance.error_message = "Erro ao verificar status do processamento"
                instance.save()

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        forms_ia_request = serializer.save(created_by=request.user)

        stage = credentials.stage.upper()
        api_credentials = get_forms_ia_credentials(stage)

        # add formatted prompt to forms_ia_request, for better context to all requests to bedrock
        formatted_prompt = f"""[INSTRUÇÕES TÉCNICAS - NÃO MENCIONAR NO CLIENT_REASONING]
            Configure o campo displayName (fora de fields e groups) com o valor exato: '{forms_ia_request.name}'

            [TAREFA DO USUÁRIO]
            {forms_ia_request.input_text}

            [FORMATO DA RESPOSTA]
            IMPORTANTE: O campo 'client_reasoning' deve ficar FORA do objeto 'form_fields', no nível raiz.
            Estrutura esperada:
            {{
              "form_fields": {{
                "displayName": "...",
                "fields": [...],
                "groups": [...],
                "measurementColumns": [...],
              }},
              "client_reasoning": "seu texto aqui"
            }}

            No 'client_reasoning', explique de forma amigável e direta:
            - Quais campos você criou e por quê
            - Como você organizou os grupos
            - Qual a utilidade prática do formulário
            - Não use termos e jargões em inglês
            Não mencione aspectos técnicos como displayName, apiName, ou estrutura JSON."""

        bedrock_payload = {
            "company_uuid": str(forms_ia_request.company.uuid),
            "input": formatted_prompt,
        }

        headers = {"x-api-key": api_credentials["api_key"]}
        bedrock_response = requests.post(
            api_credentials["api_url"],
            json=bedrock_payload,
            headers=headers,
            timeout=30,
        )

        if bedrock_response.status_code != 200:
            logger.error(
                f"Bedrock API error: {bedrock_response.status_code} - {bedrock_response.text}"
            )
            forms_ia_request.error = True
            forms_ia_request.error_message = "Erro ao iniciar processamento"
            forms_ia_request.save()
            return Response(
                {"error": "Failed to initiate Bedrock processing"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        bedrock_data = bedrock_response.json()
        request_id = bedrock_data.get("request_id")

        if not request_id:
            logger.error(f"No request_id in Bedrock response: {bedrock_data}")
            forms_ia_request.error = True
            forms_ia_request.error_message = "Resposta inválida do processamento"
            forms_ia_request.save()
            return Response(
                {"error": "Invalid response from Bedrock API"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        forms_ia_request.request_id = request_id
        forms_ia_request.save()

        response_serializer = FormsIARequestCreateSerializer(forms_ia_request)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
