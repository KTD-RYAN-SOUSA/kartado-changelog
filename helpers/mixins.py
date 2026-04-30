from django.core.exceptions import ObjectDoesNotExist
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from fnc.mappings import get
from rest_framework_json_api import serializers


class UUIDMixin:
    def validate_uuid(self, value):
        action = get("_context.view.action", self, default="")

        if action == "create":
            try:
                self.Meta.model.objects.get(uuid=value)
            except ObjectDoesNotExist:
                pass
            else:
                raise serializers.ValidationError(
                    "Já existe um objeto com este identificador."
                )

        return value


class EagerLoadingMixin:
    """
    Sets up eager loading for serializers
    """

    @classmethod
    def setup_eager_loading(cls, queryset):
        if hasattr(cls, "_SELECT_RELATED_FIELDS"):
            queryset = queryset.select_related(*cls._SELECT_RELATED_FIELDS)
        if hasattr(cls, "_PREFETCH_RELATED_FIELDS"):
            queryset = queryset.prefetch_related(*cls._PREFETCH_RELATED_FIELDS)

        return queryset


class ListCacheMixin:
    cache_timeout = 60 * 60  # Valor padrão: 1 hora

    @method_decorator(
        vary_on_headers("Authorization")
    )  # Varia com base no token do usuário
    @method_decorator(
        vary_on_headers("X-Invalidate-Cache")
    )  # Varia com base em um header customizado para invalidar o cache
    def list(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return super().list(request, *args, **kwargs)
        # Decorar o método no tempo de execução usando cache_timeout
        return cache_page(self.cache_timeout)(super().list)(request, *args, **kwargs)


class RetrieveCacheMixin:
    cache_timeout = 60 * 60  # Valor padrão: 1 hora

    @method_decorator(
        vary_on_headers("Authorization")
    )  # Varia com base no token do usuário
    @method_decorator(
        vary_on_headers("X-Invalidate-Cache")
    )  # Varia com base em um header customizado para invalidar o cache
    def retrieve(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return super().retrieve(request, *args, **kwargs)
        # Decorar o método no tempo de execução usando cache_timeout
        # O cache varia automaticamente pelo pk do objeto através do URL
        return cache_page(self.cache_timeout)(super().retrieve)(
            request, *args, **kwargs
        )
