from django.contrib import admin

from . import models


class QueuedEmailAdmin(admin.ModelAdmin):
    model = models.QueuedEmail
    autocomplete_fields = (
        "company",
        "send_to_users",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "company",
                    "send_to_users",
                    "title",
                    "content_plain_text",
                    "content_html",
                    "cleared",
                    "in_progress",
                    "sent",
                    "error",
                    "sent_at",
                    "send_anyway",
                    "custom_headers",
                )
            },
        ),
    )


admin.site.register(models.QueuedEmail, QueuedEmailAdmin)
admin.site.register(models.EmailBlacklist)
admin.site.register(models.QueuedEmailEvent)
