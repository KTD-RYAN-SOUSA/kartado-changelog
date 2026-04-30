from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse

from .models import MLPredictionConfig
from .services import fetch_predictions


class MLPredictionConfigAdmin(admin.ModelAdmin):
    list_display = ["company"]
    autocomplete_fields = ["company"]
    change_list_template = "ml_predictions_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "fetch/",
                self.admin_site.admin_view(self.fetch_view),
                name="ml_predictions_fetch",
            ),
        ]
        return custom_urls + urls

    def fetch_view(self, request):
        if request.user.is_staff and request.user.is_superuser:
            fetch_predictions()
            messages.success(
                request,
                "Busca de predições está ocorrendo em background e pode levar alguns minutos para ser concluída.",
            )
        else:
            messages.error(request, "Sem permissão.")

        return redirect(reverse("admin:ml_predictions_mlpredictionconfig_changelist"))


admin.site.register(MLPredictionConfig, MLPredictionConfigAdmin)
