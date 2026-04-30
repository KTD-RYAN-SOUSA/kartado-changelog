from django.contrib import admin

from . import models

admin.site.register(models.Job)
admin.site.register(models.JobAsyncBatch)
admin.site.register(models.NoticeViewManager)
admin.site.register(models.UserNoticeView)
