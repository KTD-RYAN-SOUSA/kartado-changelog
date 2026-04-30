from django.db import migrations


def create_job_notice_view_manager(apps, schema_editor):

    db_alias = schema_editor.connection.alias
    NoticeViewManager = apps.get_model("work_plans", "NoticeViewManager")

    kwargs = {"notice": "JOB0001", "views_quantity_limit": 3}
    NoticeViewManager.objects.using(db_alias).create(**kwargs)


class Migration(migrations.Migration):

    dependencies = [("work_plans", "0016_noticeviewmanager")]

    operations = [
        migrations.RunPython(
            create_job_notice_view_manager,
            reverse_code=migrations.RunPython.noop,
        )
    ]
