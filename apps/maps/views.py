import gzip
import json
import os
import uuid
from base64 import b64decode
from datetime import timedelta
from itertools import chain
from typing import List, Optional

import boto3
import requests
from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters import rest_framework as filters
from fnc.mappings import get
from fnc.sequences import find
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceRecord
from apps.reportings.models import Reporting
from apps.service_orders.models import ServiceOrder
from apps.templates.models import ExportRequest
from apps.work_plans.models import Job
from helpers.apps.reportings import return_select_value
from helpers.dates import request_with_timeout
from helpers.error_messages import error_message
from helpers.filters import UUIDListFilter, filter_by_obj_id
from helpers.mixins import ListCacheMixin
from helpers.pagination import CustomPagination
from helpers.permissions import PermissionManager, join_queryset
from helpers.strings import (
    build_ecm_query,
    clean_latin_string,
    get_location,
    get_value_from_obj,
)
from RoadLabsAPI.settings import credentials

from .models import ShapeFile, TileLayer
from .permissions import (
    ECMPermissions,
    EngieSearchPermissions,
    ShapeFilePermissions,
    TileLayerPermissions,
)
from .serializers import (
    ShapeFileObjectSerializer,
    ShapeFileSerializer,
    TileLayerSerializer,
)


class ChainWithLen:
    def __init__(self, *querysets):
        self.querysets = querysets
        self._len = None

    def __iter__(self):
        return chain(*self.querysets)

    def __len__(self):
        if self._len is None:
            self._len = sum(
                len(qs) if not hasattr(qs, "count") else qs.count()
                for qs in self.querysets
            )
        return self._len

    def __getitem__(self, key):
        if isinstance(key, slice):
            start, stop = key.start or 0, key.stop
            result = []
            current_pos = 0

            for qs in self.querysets:
                qs_len = len(qs) if not hasattr(qs, "count") else qs.count()

                # Skip querysets before the slice
                if current_pos + qs_len <= start:
                    current_pos += qs_len
                    continue

                # Calculate slice for this queryset
                qs_start = max(0, start - current_pos)
                qs_stop = stop - current_pos if stop is not None else None

                if hasattr(qs, "model"):
                    # É um queryset do Django
                    result.extend(qs[qs_start:qs_stop])
                else:
                    # É uma lista ou outro iterável
                    result.extend(list(qs)[qs_start:qs_stop])

                current_pos += qs_len
                if stop is not None and current_pos >= stop:
                    break

            return result
        else:
            # Para índices individuais
            for qs in self.querysets:
                qs_len = len(qs) if not hasattr(qs, "count") else qs.count()
                if key < qs_len:
                    return qs[key]
                key -= qs_len
            raise IndexError("Index out of range")


class TileLayerFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = filters.CharFilter(field_name="companies", distinct=True)


class TileLayerViewSet(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = TileLayerSerializer
    filterset_class = TileLayerFilter
    permissions = None
    ordering = "uuid"

    def get_permissions(self):
        if self.action == "styles_json":
            self.permission_classes = []
        else:
            self.permission_classes = [IsAuthenticated, TileLayerPermissions]

        return super(TileLayerViewSet, self).get_permissions()

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return TileLayer.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="TileLayer",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, TileLayer.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset, TileLayer.objects.filter(companies=user_company)
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset, TileLayer.objects.filter(companies=user_company)
                )

        elif self.action == "styles_json":
            queryset = TileLayer.objects.filter(
                pk=self.request.parser_context["kwargs"]["pk"]
            )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = TileLayer.objects.filter(companies__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="styles.json", detail=True)
    def styles_json(self, request, pk=None):
        obj = self.get_object()
        return JsonResponse(obj.mapbox_styles)


class ShapeFileFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = filters.CharFilter(field_name="companies", distinct=True)
    empty_shape = filters.BooleanFilter(field_name="geometry", lookup_expr="isnull")
    parent = UUIDListFilter()

    class Meta:
        model = ShapeFile
        fields = {"name": ["exact", "icontains"]}


class ShapeFileViewSet(ListCacheMixin, viewsets.ModelViewSet):
    serializer_class = ShapeFileSerializer
    permission_classes = [IsAuthenticated, ShapeFilePermissions]
    filterset_class = ShapeFileFilter
    permissions = None
    ordering = "uuid"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_serializer_class(self):
        if self.action in [
            "retrieve",
            "update",
            "partial_update",
            "create",
            "get_gzip",
            "get_pbf",
        ]:
            return ShapeFileObjectSerializer
        return ShapeFileSerializer

    def get_queryset(self):
        queryset = None

        # On list action: limit queryset
        if self.action == "list":
            if "company" not in self.request.query_params:
                return ShapeFile.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ShapeFile",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ShapeFile.objects.none())
            if "self" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ShapeFile.objects.filter(
                        Q(companies=user_company)
                        & (
                            Q(private=False)
                            | (Q(private=True) & Q(created_by=self.request.user))
                        )
                    ),
                )
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ShapeFile.objects.filter(
                        Q(companies=user_company)
                        & (
                            Q(private=False)
                            | (Q(private=True) & Q(created_by=self.request.user))
                        )
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = queryset = ShapeFile.objects.filter(
                Q(companies__in=user_companies)
                & (
                    Q(private=False)
                    | (Q(private=True) & Q(created_by=self.request.user))
                )
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["get"], url_path="GZIP", detail=True)
    def get_gzip(self, request, pk=None):
        queryset = self.get_queryset()
        shape_file = get_object_or_404(queryset, pk=pk)

        feature_collection_field = self.get_serializer().fields["feature_collection"]
        try:
            feature_collection = feature_collection_field.to_representation(shape_file)
        except Exception:
            feature_collection = None

        if feature_collection:
            features = feature_collection.get("features", [])
            if features:
                for item in features:
                    if isinstance(item, dict):
                        properties = item.get("properties", {})
                        obj_id = properties.get("OBJECTID", "")
                        properties["uuid"] = "{}-{}".format(
                            str(shape_file.uuid), obj_id
                        )
                        item["properties"] = properties
                feature_collection["features"] = features

            json_response = JsonResponse(feature_collection)
            compressed_content = gzip.compress(json_response.content)

            response = HttpResponse(compressed_content, content_type="application/gzip")
            response["Content-Encoding"] = "gzip"
            response[
                "Content-Disposition"
            ] = f'attachment; filename="{shape_file.name}.json"'

            return response
        else:
            return HttpResponse(status=204)

    @action(methods=["get"], url_path="PBF", detail=True)
    def get_pbf(self, request, pk=None):
        queryset = self.get_queryset()
        shape_file = get_object_or_404(queryset, pk=pk)

        feature_collection_field = self.get_serializer().fields["feature_collection"]
        try:
            feature_collection = feature_collection_field.to_representation(shape_file)
        except Exception:
            feature_collection = None

        if feature_collection:
            features = feature_collection.get("features", [])
            if features:
                for item in features:
                    if isinstance(item, dict):
                        properties = item.get("properties", {})
                        obj_id = properties.get("OBJECTID", "")
                        properties["uuid"] = "{}-{}".format(
                            str(shape_file.uuid), obj_id
                        )
                        item["properties"] = properties
                feature_collection["features"] = features
            json_response = JsonResponse(feature_collection)
            compressed_content = gzip.compress(json_response.content)
            response = HttpResponse(compressed_content, content_type="application/gzip")
            response["Content-Encoding"] = "gzip"
            response[
                "Content-Disposition"
            ] = f'attachment; filename="{shape_file.name}.json"'
            return response
        else:
            return HttpResponse(status=204)


class ShapeFilePropertyViewSet(viewsets.ViewSet):
    """
    Example empty viewset demonstrating the standard
    actions that will be handled by a router class.

    If you're using format suffixes, make sure to also include
    the `format=None` keyword argument for each action.
    """

    def list(self, request):
        forbidden_response = Response(
            data=[
                {
                    "detail": "Você não tem permissão para executar essa ação.",
                    "source": {"pointer": "/data"},
                    "status": status.HTTP_403_FORBIDDEN,
                }
            ],
            status=status.HTTP_403_FORBIDDEN,
        )

        if "company" not in request.query_params:
            return forbidden_response
        else:
            try:
                company = Company.objects.get(uuid=request.query_params["company"])
                properties_shape_id = company.metadata["properties_shape"]
                properties_shape = ShapeFile.objects.get(uuid=properties_shape_id)
            except Exception:
                return forbidden_response

        page_size = None
        if "page_size" in request.query_params:
            page_size = int(request.query_params["page_size"])

        properties = [
            {"index": i, **a} for i, a in enumerate(properties_shape.properties)
        ]

        shape_file_fields = get(
            "metadata.arcgis_layer_info.fields", properties_shape, default=[]
        )

        all_fields = {x["name"]: x for x in shape_file_fields}

        for field in shape_file_fields:
            if field["name"] in request.query_params:
                filter_words = [
                    clean_latin_string(a.lower())
                    for a in request.query_params[field["name"]].split(" ")
                ]
                if any(filter_words):
                    properties = [
                        a
                        for a in properties
                        if all(
                            search_word
                            in clean_latin_string((a[field["name"]] or "").lower())
                            for search_word in filter_words
                        )
                    ]

        if "search" in request.query_params:
            search = [
                clean_latin_string(a.lower())
                for a in request.query_params["search"].split(" ")
            ]
            if any(search):
                properties = [
                    a
                    for a in properties
                    if all(
                        search_word
                        in clean_latin_string(
                            "".join([str(b) for b in a.values() if b]).lower()
                        )
                        for search_word in search
                    )
                ]
        if "id" in request.query_params:
            try:
                id_find = (request.query_params.get("id", "")).split("-")[-1]
                properties = [
                    item for item in properties if str(item.get("OBJECTID")) == id_find
                ]
            except Exception:
                properties = []

        if page_size:
            properties = (
                properties[:page_size] if len(properties) > page_size else properties
            )

        translated_properties = []
        for original_property in properties:
            translated_property = {}
            for key, value in original_property.items():
                if key == "index":
                    translated_property[key] = value
                    continue
                field = all_fields[key]
                text = value if value is not None else ""
                domain_coded_values = get("domain.codedValues", field)
                if domain_coded_values:
                    domain_option = find(
                        lambda a: a["code"] == value, domain_coded_values
                    )
                    text = domain_option["name"] if domain_option else text
                translated_property[key] = text
            translated_properties.append(translated_property)

        result_properties = [
            {
                "id": "{}-{}".format(properties_shape_id, a["OBJECTID"]),
                "type": "ShapeFileProperty",
                "attributes": {
                    "uuid": "{}-{}".format(properties_shape_id, a["OBJECTID"]),
                    "centroid": json.loads(
                        properties_shape.geometry[a["index"]].centroid.json
                    ),
                    **a,
                },
                "relationships": {
                    "shapeFile": {
                        "data": {"type": "ShapeFile", "id": properties_shape_id}
                    }
                },
            }
            for a in translated_properties
        ]

        return Response(data=result_properties, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        pass


class EngieSearchView(APIView):
    """
    API view to handle integration with Engie APR software.

    This view processes GET requests to retrieve various types of records
    (OccurrenceRecord, ServiceOrder, Reporting, Job) based on the permissions
    of the authenticated user and the provided query parameters.

    Attributes:
        action (str): The action type, default is "list".
        permissions (None): Placeholder for permissions, default is None.
        permission_classes (tuple): Tuple containing the permission classes
            required for this view.

    Methods:
        get(request, format=None):
            Handles GET requests to retrieve and filter records based on
            user permissions and query parameters.
    """

    action: str = "list"
    permissions: Optional[None] = None
    permission_classes: tuple = (IsAuthenticated, EngieSearchPermissions)

    def get(self, request, format: Optional[str] = None) -> Response:
        empty_response = Response({"type": "EngieSearch", "attributes": []})

        companies_with_permission: List[str] = []
        for perm in self.permission_classes:
            if hasattr(perm, "companies_with_permission"):
                companies_with_permission = perm.companies_with_permission

        if not companies_with_permission:
            return empty_response

        companies_metadatas = Company.objects.filter(
            uuid__in=companies_with_permission
        ).values_list("metadata", flat=True)

        status: List[str] = [
            a
            for item in companies_metadatas
            if "sst_forms_status" in item
            for a in item["sst_forms_status"]
        ]

        numero: str = request.query_params.get("numero", "")

        usina: str = request.query_params.get("usina", "")

        objs_registros_filter: dict = {
            "company_id__in": companies_with_permission,
            "status_id__in": status,
        }
        objs_servicos_filter: dict = {
            "company_id__in": companies_with_permission,
            "is_closed": False,
        }
        objs_apontamentos_filter: dict = {
            "company_id__in": companies_with_permission,
            "status_id__in": status,
        }
        objs_programacoes_filter: dict = {
            "company_id__in": companies_with_permission,
        }
        if numero:
            objs_registros_filter["number__in"] = numero.split(",")
            objs_servicos_filter["number__in"] = numero.split(",")

        if usina:
            usina_list: List[str] = usina.split(",")

            usinas_prefix: List[str] = Company.objects.filter(
                uuid__in=companies_with_permission
            ).values_list("metadata__company_prefix", flat=True)

            usinas_with_permission: List[str] = [
                a for a in usina_list if a in usinas_prefix
            ]
            objs_registros_filter[
                "company__metadata__company_prefix__in"
            ] = usinas_with_permission
            objs_servicos_filter[
                "company__metadata__company_prefix__in"
            ] = usinas_with_permission
            objs_apontamentos_filter[
                "company__metadata__company_prefix__in"
            ] = usinas_with_permission
            objs_programacoes_filter[
                "company__metadata__company_prefix__in"
            ] = usinas_with_permission

        objs_registros = (
            OccurrenceRecord.objects.filter(**objs_registros_filter)
            .prefetch_related(
                "city",
                "location",
                "river",
                "company",
                "occurrence_type",
            )
            .distinct()
            .order_by("uuid")
            .only(
                "uuid",
                "number",
                "company_id",
                "occurrence_type_id",
                "form_data",
                "city_id",
                "location_id",
                "river_id",
                "uf_code",
                "place_on_dam",
            )
        )
        objs_servicos = (
            ServiceOrder.objects.filter(**objs_servicos_filter)
            .prefetch_related("city", "location", "river", "company")
            .distinct()
            .order_by("uuid")
        )
        objs_apontamentos = (
            Reporting.objects.filter(**objs_apontamentos_filter)
            .prefetch_related("status", "company", "occurrence_type")
            .distinct()
            .order_by("uuid")
        )
        objs_programacoes = (
            Job.objects.filter(**objs_programacoes_filter)
            .prefetch_related(
                "reportings", "reportings__company", "reportings__occurrence_type"
            )
            .distinct()
            .order_by("uuid")
        )

        objs_data = ChainWithLen(
            objs_registros, objs_servicos, objs_apontamentos, objs_programacoes
        )
        paginator_class = CustomPagination()
        page = paginator_class.paginate_queryset(objs_data, request)

        possible_path_kind: str = (
            "occurrencerecord__fields__occurrencekind__selectoptions__options"
        )
        data: List[dict] = []
        for item in page:
            obj_type: str = item._meta.model_name
            if obj_type == "occurrencerecord" and item:
                data.append(
                    {
                        "tipo": "registro",
                        "numero": item.number,
                        "titulo": "{}, {}".format(
                            (
                                "{}, {}".format(
                                    get_value_from_obj(
                                        item.company.custom_options,
                                        possible_path_kind,
                                        item.occurrence_type.occurrence_kind,
                                    ),
                                    item.occurrence_type.name,
                                )
                                if item.occurrence_type
                                else ""
                            ),
                            item.form_data.get("action", ""),
                        ),
                        "localizacao": get_location(item, obj_type),
                        "link": "{}/#/SharedLink/{}/{}/show?company={}".format(
                            settings.FRONTEND_URL,
                            "OccurrenceRecord",
                            str(item.uuid),
                            str(item.company_id),
                        ),
                    }
                )
            elif obj_type == "serviceorder" and item:
                data.append(
                    {
                        "tipo": "servico",
                        "numero": item.number,
                        "titulo": item.description,
                        "localizacao": get_location(item, obj_type),
                        "link": "{}/#/SharedLink/ServiceOrder/{}/show?company={}".format(
                            settings.FRONTEND_URL,
                            str(item.uuid),
                            str(item.company_id),
                        ),
                    }
                )
            elif obj_type == "reporting" and item:
                data.append(
                    {
                        "tipo": "apontamento",
                        "numero": item.number,
                        "titulo": get_value_from_obj(
                            item.company.custom_options,
                            "reporting__fields__occurrencekind__selectoptions__options",
                            item.occurrence_type.occurrence_kind,
                        )
                        + ", "
                        + item.occurrence_type.name,
                        "localizacao": get_location(item, obj_type),
                        "ativo": return_select_value("active", item, {}),
                        "link": "{}/#/SharedLink/Reporting/{}?company={}".format(
                            settings.FRONTEND_URL,
                            str(item.uuid),
                            str(item.company_id),
                        ),
                    }
                )
            elif obj_type == "job" and item:
                primeiro_apontamento: Optional[Reporting] = (
                    item.reportings.all()[0] if len(item.reportings.all()) > 0 else None
                )
                data.append(
                    {
                        "tipo": "programacao",
                        "numero": item.number,
                        "titulo": item.title,
                        "localizacao": get_location(primeiro_apontamento, "reporting")
                        if primeiro_apontamento
                        else "",
                        "data_inicial": item.start_date.strftime("%d/%m/%Y"),
                        "data_final": item.end_date.strftime("%d/%m/%Y"),
                        "ativo": return_select_value("active", primeiro_apontamento, {})
                        if primeiro_apontamento
                        else "",
                        "link": "{}/#/SharedLink/Job/{}/show?company={}".format(
                            settings.FRONTEND_URL,
                            str(item.uuid),
                            str(item.company_id),
                        ),
                    }
                )

        if data:
            return paginator_class.get_paginated_response(data)

        return Response(data)


class EcmSearchView(APIView):
    action = "list"
    permissions = None
    permission_classes = (IsAuthenticated, ECMPermissions)

    def get(self, request, format=None):
        fields = ["company", "shape_file_property"]
        allowed_search_types = ["registro", "imovel"]
        response_failed = Response({"type": "EcmSearch", "attributes": []})

        if not set(fields).issubset(request.query_params.keys()):
            return response_failed

        shape_file_splitted = request.query_params.get("shape_file_property", "").split(
            "-"
        )
        property_obj_id = shape_file_splitted.pop()
        shape_file_id = "-".join(shape_file_splitted)

        try:
            shape_file_uuid = uuid.UUID(shape_file_id)
            shape_file = ShapeFile.objects.get(pk=shape_file_uuid)
        except Exception:
            return error_message(400, "ShapeFile não encontrado.")
        else:
            search_type = shape_file.metadata.get("ecmSearchType", "")

        if search_type not in allowed_search_types:
            return error_message(400, "SearchType inválido.")

        # Get features
        try:
            feature_collection_field = ShapeFileObjectSerializer().fields[
                "feature_collection"
            ]
            features = feature_collection_field.to_representation(shape_file)[
                "features"
            ]
        except Exception:
            features = []

        # Get properties
        try:
            properties = list(
                filter(
                    lambda item: filter_by_obj_id(item, int(property_obj_id)),
                    features,
                )
            )[0]
            properties_dict = {
                k.lower(): v for k, v in properties["properties"].items()
            }
        except Exception:
            return error_message(400, "Propriedade não encontrada.")

        if search_type == "registro":
            dDocTitle = str(properties_dict.get("numero", ""))
            xcDPSimobTipo = str(properties_dict.get("tipo", ""))
            if xcDPSimobTipo and dDocTitle:
                values = [
                    {
                        "campo": "xIdcProfile",
                        "valor": "DPSPatrimonioImob",
                        "operacao": "AND",
                    },
                    {
                        "campo": "dDocTitle",
                        "valor": dDocTitle,
                        "operacao": "AND",
                    },
                    {
                        "campo": "xcDPSimobTipo",
                        "valor": xcDPSimobTipo,
                        "operacao": "AND",
                    },
                    {
                        "campo": "xcDPSimobTipoDocumento",
                        "valor": "Registro de Ocorrência Sócio Patrimonial",
                        "operacao": "AND",
                    },
                ]
            else:
                return error_message(400, "Erro no ECM request data.")
        elif search_type == "imovel":
            xcDPSimobObra = str(properties_dict.get("obra", ""))
            xcDPSimobSequencial = str(properties_dict.get("sequencial", ""))
            dDocTitle = str(properties_dict.get("identificador", ""))
            if xcDPSimobObra and xcDPSimobSequencial and dDocTitle:
                values = [
                    {
                        "campo": "xIdcProfile",
                        "valor": "DPSPatrimonioImob",
                        "operacao": "AND",
                    },
                    {
                        "campo": "xcDPSimobObra",
                        "valor": xcDPSimobObra,
                        "operacao": "AND",
                    },
                    {
                        "campo": "xcDPSimobSequencial",
                        "valor": xcDPSimobSequencial,
                        "operacao": "AND",
                    },
                    {
                        "campo": "xcDPSimobTipoDocumento",
                        "valor": "Processo Patrimonial",
                        "operacao": "OR",
                    },
                    {
                        "campo": "dDocTitle",
                        "valor": dDocTitle,
                        "operacao": "OR",
                    },
                    {
                        "campo": "xcDPSimobIdentificador",
                        "valor": dDocTitle,
                        "operacao": "AND",
                    },
                ]
            else:
                return error_message(400, "Erro no ECM request data.")
        else:
            return response_failed

        url = credentials.ECM_SEARCH_EXTERNAL_URL

        data = {
            "valores": values,
            "tipoPesquisa": "advanced",
            "sistema": "KARTADO",
            "resultCount": 5000,
        }
        headers = {
            "Authorization": "Basic " + credentials.ECM_LOGIN_TOKEN,
            "Content-Type": "application/json",
        }

        send_post = requests.post(url, data=json.dumps(data), headers=headers)

        if send_post.status_code == 200:
            context = send_post.json()
            context["search_url"] = build_ecm_query(values, search_type)
            context["search_body"] = values
            return Response(data=context, status=status.HTTP_200_OK)
        else:
            return error_message(400, "Erro no ECM request.")


class EcmDownloadView(APIView):
    action = "list"
    permissions = None
    permission_classes = (IsAuthenticated, ECMPermissions)

    def get(self, request, format=None):
        fields = ["company", "document_id"]
        response_failed = Response({"type": "EcmDownload", "attributes": []})

        if not set(fields).issubset(request.query_params.keys()):
            return response_failed

        url = credentials.ECM_DOWNLOAD_EXTERNAL_URL

        document_id = request.query_params.get("document_id", "")
        if document_id:
            data = {"dID": document_id, "sistema": "KARTADO"}
        else:
            return error_message(400, "Erro no ECM request data.")

        headers = {
            "Authorization": "Basic " + credentials.ECM_LOGIN_TOKEN,
            "Content-Type": "application/json",
        }

        try:
            timeout = 20
            send_post = request_with_timeout(
                requests.post,
                url=url,
                data=json.dumps(data),
                headers=headers,
                kwargs={"timeout": timeout},
                timeout=timeout,
            )
        except Exception:
            return error_message(400, "Timeout no ECM request")

        if send_post.status_code != 200:
            return error_message(400, "Erro no ECM request")

        try:
            context = send_post.json()
            download_file = context["downloadFile"]
            file_name = download_file["fileName"]
            file_content = download_file["fileContent"]
        except Exception:
            return error_message(400, "Variáveis do download inválidas")

        if not file_content or not file_name:
            return error_message(400, "Erro no download do arquivo: arquivo não existe")

        # Create a temporary folder
        path = "/tmp/"
        os.makedirs(path, exist_ok=True)
        path_file_total = clean_latin_string(path + file_name).replace(" ", "_")

        # Save file
        byte_file = b64decode(file_content, validate=True)
        f = open(path_file_total, "wb")
        f.write(byte_file)
        f.close()

        # Create ExportRequest object
        obj = ExportRequest.objects.create(
            company_id=request.query_params.get("company", ""),
            created_by=request.user,
            json_zip=context,
        )

        # Upload the file to S3, setting a header to make it expire in 6 hours
        bucket_name = credentials.AWS_STORAGE_ENGIE_PRODUCTION_BUCKET_NAME
        expires = timezone.now() + timedelta(hours=6)
        object_name = "media/private/{}".format(file_name)

        s3 = boto3.client(
            "s3",
            aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
            aws_session_token=credentials.AWS_SESSION_TOKEN,
        )

        try:
            s3.upload_file(
                path_file_total,
                bucket_name,
                object_name,
                ExtraArgs={"Expires": expires},
            )
        except Exception:
            obj.error = True
        else:
            # Delete file
            os.remove(path_file_total)

            url_s3 = s3.generate_presigned_url(
                "get_object", Params={"Bucket": bucket_name, "Key": object_name}
            )
            obj.url = url_s3
            obj.done = True

        obj.save()

        return Response(data={"url_s3": url_s3}, status=status.HTTP_200_OK)


class EcmCheckPermissionView(APIView):
    action = "list"
    permissions = None
    permission_classes = (IsAuthenticated,)

    def get(self, request, format=None):
        permissions = ECMPermissions()
        has_permission = permissions.has_permission(request, self)

        return Response(
            {
                "type": "EcmCheckPermission",
                "attributes": {"canView": has_permission},
            }
        )
