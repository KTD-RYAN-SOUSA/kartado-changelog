import logging

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver
from fieldsignals.signals import post_save_changed
from simple_history.signals import pre_create_historical_record

from apps.companies.models import UserInCompany
from apps.templates.signals import post_save_action
from apps.users.models import User
from helpers.apps.arcgis import ArcGisSync
from helpers.apps.occurrence_records import (
    add_occurrence_record_changes_debounce_data,
    handle_reading_notification,
)
from helpers.apps.todo import field_has_changed, mark_to_dos_as_read
from helpers.apps.vg import VGSync
from helpers.middlewares import get_current_user
from helpers.permissions import PermissionManager
from helpers.signals import (
    DisableSignals,
    disable_signal_for_loaddata,
    generic_fill_km_field,
    history_dont_save_geometry_changes,
    watcher_email_notification,
)
from helpers.strings import clean_latin_string, get_autonumber_array, get_obj_from_path

from .models import (
    HistoricalOccurrenceRecord,
    OccurrenceRecord,
    OccurrenceRecordWatcher,
    OccurrenceType,
    RecordPanel,
    RecordPanelShowList,
    RecordPanelShowMobileMap,
    RecordPanelShowWebMap,
)
from .notifications import average_flow


@receiver(pre_save, sender=OccurrenceRecord)
def auto_add_ro_name(sender, instance, **kwargs):
    if instance.number in [None, ""]:
        instance_type = "RO"
        key_name = "{}_name_format".format(instance_type)
        # Get datetime and serial arrays
        data = get_autonumber_array(instance.company.uuid, instance_type)
        # Get company prefix
        if "company_prefix" in instance.company.metadata:
            data["prefixo"] = instance.company.metadata["company_prefix"]
        else:
            data["prefixo"] = "[{}]".format(instance.company.name)
        # Make number
        try:
            if key_name in instance.company.metadata:
                number = instance.company.metadata[key_name].format(**data)
            else:
                raise Exception("Variáveis de nome inválidas!")
        except Exception as e:
            print(e)
            # Fallback
            # UHIT-RG-2018.0001
            number = "{prefixo}-{nome}-{anoCompleto}.{serialAno}".format(**data)

        instance.number = number


@receiver(pre_save, sender=OccurrenceRecord)
def fill_km_field(sender, instance, **kwargs):
    generic_fill_km_field(instance, instance.company)


@receiver(post_save, sender=OccurrenceRecord)
@disable_signal_for_loaddata
def update_editable_field(sender, instance, created, **kwargs):
    if instance.status:
        company = instance.company
        lock_occurrence_record_at = company.metadata.get(
            "lock_occurrence_record_at", []
        )
        unlock_occurrence_record_at = company.metadata.get(
            "unlock_occurrence_record_at", []
        )

        if instance.operational_control:
            # operational record is always editable
            return
        elif str(instance.status.uuid) in lock_occurrence_record_at:
            instance.editable = False
        elif str(instance.status.uuid) in unlock_occurrence_record_at:
            instance.editable = True
        else:
            # if no change in fields, no need to save the instance. return.
            return

        # disconnect signal to avoid recursion on update
        post_save.disconnect(update_editable_field, sender=sender)
        post_save.disconnect(post_save_action, sender=sender)
        instance.save()
        post_save.connect(update_editable_field, sender=sender)
        post_save.connect(post_save_action, sender=sender)


@receiver(post_save, sender=OccurrenceRecord)
@disable_signal_for_loaddata
def call_arcgis_sync(sender, instance, created, **kwargs):
    if settings.ARCGIS_SYNC_ENABLE:
        arcgis_sync = ArcGisSync(instance, created)
        record = arcgis_sync.process_sync()

        # disconnect signal to avoid recursion on update
        with DisableSignals():
            record.save()


@receiver(post_save, sender=OccurrenceRecord)
def send_obj_to_api(sender, instance, created, **kwargs):
    try:
        possible_path = "operationalcontrol__fields__kind__selectoptions__options"
        options = get_obj_from_path(instance.company.custom_options, possible_path)
        kind = {
            clean_latin_string(item["name"].lower()): item["value"] for item in options
        }["residuos"]
    except Exception:
        pass
    else:
        if (
            instance.operational_control
            and instance.operational_control.kind == kind
            and instance.occurrence_type
            and instance.occurrence_type.occurrence_kind == kind
            and "name" in instance.occurrence_type.form_fields
            and instance.occurrence_type.form_fields["name"] == "geracaoDeResiduo"
        ):
            if created or instance.editable:
                record = VGSync(instance, retry=instance.editable).process_sync()

                # disconnect signal to avoid recursion on update
                with DisableSignals():
                    record.save()


@receiver(pre_create_historical_record, sender=HistoricalOccurrenceRecord)
def dont_save_geometry_changes(sender, instance, history_instance, **kwargs):
    history_dont_save_geometry_changes(history_instance)


@receiver(post_save, sender=OccurrenceRecord)
def average_flow_notifications(sender, instance, created, **kwargs):
    water_meter_uuid = instance.form_data.get("records", "")

    # Is it a water meter consumption record being created?
    if created and water_meter_uuid and instance.operational_control:
        try:
            # Get water meter record
            water_meter = OccurrenceRecord.objects.get(uuid=water_meter_uuid)
        except Exception:
            pass
        else:
            average_flow(instance, water_meter, water_meter_uuid)


@receiver(post_save, sender=OccurrenceRecord)
def notify_occurrence_record_update(sender, instance, created, **kwargs):
    """
    Notify OccurrenceRecord creation or update
    """

    add_occurrence_record_changes_debounce_data(instance, created)


def check_permission(model: str, permission: str, all_permissions: dict) -> bool:
    try:
        return all_permissions[model][permission][0]
    except Exception as error:
        print(error)
        return False


@receiver(pre_save, sender=RecordPanel)
def auto_fill_content_type(sender, instance, **kwargs):
    user = get_current_user()

    permissions = PermissionManager(
        user=user,
        company_ids=instance.get_company_id,
        model="RecordPanel",
    )
    if check_permission("reporting", "can_view", permissions.all_permissions):
        instance.content_type = ContentType.objects.get(
            app_label="reportings", model="reporting"
        )
    else:
        instance.content_type = ContentType.objects.get(
            app_label="occurrence_records", model="occurrencerecord"
        )


@receiver(m2m_changed, sender=RecordPanel.viewer_users.through)
@receiver(m2m_changed, sender=RecordPanel.editor_users.through)
def manage_panel_show_maps(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        for user_id in pk_set:
            user = User.objects.get(pk=user_id)

            if user == instance.created_by:
                continue
            is_viewer = instance.viewer_users.filter(pk=user.pk).exists()
            is_editor = instance.editor_users.filter(pk=user.pk).exists()

            has_web_map = RecordPanelShowWebMap.objects.filter(
                user=user, panel=instance
            ).exists()
            has_mobile_map = RecordPanelShowMobileMap.objects.filter(
                user=user, panel=instance
            ).exists()

            if (is_viewer and is_editor) and (not has_web_map or not has_mobile_map):
                continue
            if not has_web_map:
                RecordPanelShowWebMap.objects.create(user=user, panel=instance)
            if not has_mobile_map:
                RecordPanelShowMobileMap.objects.create(user=user, panel=instance)


def create_panel_show_if_not_present(record_panel, user_id_list):
    """
    mark a panel as new when it is shared with a user
    """
    for user_id in user_id_list:
        if user_id == record_panel.created_by_id:
            continue

        if not RecordPanelShowList.objects.filter(
            user_id=user_id, panel=record_panel
        ).exists():
            order = 1
            user_panels = RecordPanelShowList.objects.filter(
                user_id=user_id,
                panel__menu=record_panel.menu,
            ).order_by("-order")
            if user_panels.exists():
                order = user_panels.first().order + 1

            RecordPanelShowList.objects.create(
                user_id=user_id, panel=record_panel, new_to_user=True, order=order
            )


@receiver(m2m_changed, sender=RecordPanel.viewer_users.through)
@receiver(m2m_changed, sender=RecordPanel.editor_users.through)
def create_show_list(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        create_panel_show_if_not_present(instance, pk_set)


@receiver(m2m_changed, sender=RecordPanel.viewer_firms.through)
@receiver(m2m_changed, sender=RecordPanel.editor_firms.through)
def create_show_list_firm(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        user_ids = set(
            User.objects.filter(
                user_firms__in=pk_set,
            )
            .only("uuid")
            .values_list("uuid", flat=True)
        )
        create_panel_show_if_not_present(instance, list(user_ids))


@receiver(m2m_changed, sender=RecordPanel.viewer_subcompanies.through)
@receiver(m2m_changed, sender=RecordPanel.editor_subcompanies.through)
def create_show_list_subcompanies(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        user_ids = set(
            User.objects.filter(
                user_firms__subcompany__in=pk_set,
            )
            .only("uuid")
            .values_list("uuid", flat=True)
        )
        create_panel_show_if_not_present(instance, list(user_ids))


@receiver(m2m_changed, sender=RecordPanel.viewer_permissions.through)
@receiver(m2m_changed, sender=RecordPanel.editor_permissions.through)
def create_show_list_permission(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        user_ids = set(
            UserInCompany.objects.filter(
                permissions__in=pk_set,
                company=instance.company,
            ).values_list("user_id", flat=True)
        )
        create_panel_show_if_not_present(instance, list(user_ids))


@receiver(post_save, sender=OccurrenceRecord)
def notify_new_reading(sender, instance, created, **kwargs):
    """
    Inject new reading notification for users with the proper UserNotification
    configuration.

    Does not group results of multiple Company instances.
    """

    NOTIFICATION_AREA = "auscultacao.novas_leituras"

    if created and instance.form_data.get("condition", False):
        result_api_name = get_obj_from_path(
            instance.occurrence_type.form_fields, "resultapiname"
        )
        if result_api_name:
            handle_reading_notification(instance, NOTIFICATION_AREA)


@receiver(post_save_changed, sender=OccurrenceRecord)
def check_unread_todos(sender, instance, changed_fields, created, **kwargs):
    """
    Check if we have any ToDo that hasn't been marked as done,
    and if so, mark them as done
    """
    if field_has_changed(changed_fields, "approval_step"):
        mark_to_dos_as_read(instance)


@receiver(post_save_changed, sender=OccurrenceRecord)
def warn_condition_on_validated_reading(
    sender, instance, changed_fields, created, **kwargs
):
    """
    Inject reading notification when the condition warrants a warning

    Does not group results of multiple Company instances.
    """

    NOTIFICATION_AREA = "auscultacao.novas_leituras_validadas"
    WARNING_CONDITIONS = ["Alerta", "Atenção", "Emergência"]

    old_validated_at, new_validated_at = next(
        (
            (old, new)
            for field, (old, new) in changed_fields.items()
            if field == "validated_at"
        ),
        (None, None),
    )

    obj_form_data = instance.form_data
    condition = obj_form_data.get("condition", None)

    # Flags
    was_just_validated = old_validated_at is None and new_validated_at
    notifiable_condition = condition in WARNING_CONDITIONS

    if was_just_validated and notifiable_condition:
        handle_reading_notification(instance, NOTIFICATION_AREA)


@receiver(post_save_changed, sender=OccurrenceRecord)
def warn_reading_needs_to_be_remade(
    sender, instance, changed_fields, created, **kwargs
):
    """
    Notify OccurrenceRecord needs to be remade

    Does not group results of multiple Company instances.
    """

    NOTIFICATION_AREA = "auscultacao.leitura_precisa_ser_refeita"

    # Get the step uuid for remake
    remake_step_uuid = instance.company.metadata.get("remake_step", None)

    # Get the changed approval step
    _, new_approval_step = next(
        (
            (old, new)
            for field, (old, new) in changed_fields.items()
            if field == "approval_step"
        ),
        (None, None),
    )

    is_notifiable = (
        remake_step_uuid
        and isinstance(remake_step_uuid, str)
        and new_approval_step
        and remake_step_uuid == str(new_approval_step)
    )

    if is_notifiable:
        handle_reading_notification(instance, NOTIFICATION_AREA)


@receiver(post_save, sender=OccurrenceRecordWatcher)
@disable_signal_for_loaddata
def watcher_email_occ_record(
    sender, instance: OccurrenceRecordWatcher, created: bool, **kwargs
):
    """
    Notify OccurrenceRecordWatcher related to a user

    Does not group results of multiple Company instances.
    """

    NOTIFICATION_AREA = "registros.adicao_aos_notificados"

    # OccurrenceRecord specific logic to determined
    # if it's going to be notified or not
    company = instance.occurrence_record.company
    occ_type_is_not_notified = (
        instance.occurrence_record.occurrence_type
        and instance.occurrence_record.occurrence_type.occurrencetype_specs.filter(
            company=company, is_not_notified=True
        ).exists()
    )
    monitoring_plan_is_not_notified = (
        instance.occurrence_record.monitoring_plan
        and instance.occurrence_record.monitoring_plan.is_not_notified
    )
    is_not_notified = occ_type_is_not_notified or monitoring_plan_is_not_notified

    if is_not_notified:
        logging.info("The OccurrenceRecordWatcher is configured to not notify")
    else:
        watcher_email_notification(NOTIFICATION_AREA, instance, created)


@receiver(post_save, sender=OccurrenceRecord)
@disable_signal_for_loaddata
def set_altimetry(sender, instance, created, **kwargs):
    altimetry_enable = instance.company.metadata.get("altimetry_enable", False)
    if created and altimetry_enable:
        try:
            instance.set_altimetry()
        except Exception:
            pass


@receiver(post_save_changed, sender=OccurrenceRecord)
@disable_signal_for_loaddata
def update_altimetry(sender, instance, changed_fields, **kwargs):
    included_fields = [f for f in changed_fields]
    created = instance._state.adding
    geo_included = "geometry" in included_fields
    form_data_included = "form_data" in included_fields
    relevant_included = geo_included or form_data_included
    if not created and relevant_included:
        for field, (old, new) in changed_fields.items():
            if isinstance(new, dict):
                if new.get("altitude", None) is None:
                    try:
                        altimetry_enable = instance.company.metadata.get(
                            "altimetry_enable", False
                        )
                        manually_specified = (
                            instance.form_metadata.get("altitude").get(
                                "manually_specified"
                            )
                            if instance.form_metadata.get("altitude", None) is not None
                            else None
                        )
                        if altimetry_enable and not manually_specified:
                            instance.set_altimetry()
                    except Exception as err:
                        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> update_altimetry", err)

            # NOTE: This is meant to be used only when geometry field is not being changed
            elif field == "form_data" and not geo_included:
                in_new = "building" in new
                in_old = "building" in old
                new_building = new.get("building", None)
                old_building = old.get("building", None)
                if (in_new or in_old) and (new_building != old_building):
                    instance.set_altimetry()

            elif field == "geometry":
                try:
                    altimetry_enable = instance.company.metadata.get(
                        "altimetry_enable", False
                    )
                    manually_specified = (
                        instance.form_metadata.get("altitude").get("manually_specified")
                        if instance.form_metadata.get("altitude", None) is not None
                        else None
                    )
                    if altimetry_enable:
                        set_valid = False
                        if old is None and new:
                            set_valid = True
                        elif len(old.tuple) != len(new.tuple):
                            set_valid = True
                        else:
                            geo_old = old.tuple
                            geo_new = new.tuple
                            max_range = len(old.tuple)
                            for index in range(max_range):
                                if geo_old[index] != geo_new[index]:
                                    set_valid = True
                                    break
                        if set_valid:
                            instance.set_altimetry()
                except Exception as err:
                    print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> update_altimetry", err)


@receiver(post_save, sender=OccurrenceType)
def fill_custom_map_table_after_creation(sender, instance, created, **kwargs):
    if created and not instance.custom_map_table:
        # Always present
        instance.custom_map_table = ["foundAt", "number"]

        # Present for companies using roads
        company = instance.company.first()
        hide_reporting_location = (
            get_obj_from_path(company.metadata, "hidereportinglocation") is True
            if company
            else False
        )
        if hide_reporting_location is False:
            instance.custom_map_table.extend(["direction", "km"])

        # Present for occ types using notes
        fields = instance.form_fields.get("fields", [])
        if fields and isinstance(fields, list):
            for field in fields:
                if (
                    field.get("apiName", "") == "notes"
                    or field.get("api_name", "") == "notes"
                ):
                    instance.custom_map_table.append("notes")
                    break

        with DisableSignals():
            instance.save()


@receiver(pre_save, sender=OccurrenceType)
def update_custom_map_table_on_field_change(sender, instance, **kwargs):
    """
    Maintains the custom_map_table updated according to the current form_fields.
    If a field is removed from form_fields, it should also be removed from custom_map_table
    if not part of the API_NAME_WHITELIST.
    """

    # If present in the whitelist, do not remove from custom_map_table
    API_NAME_WHITELIST = [
        "km",
        "number",
        "endKm",
        "projectKm",
        "projectEndKm",
        "kmReference",
        "relationships.status.data.id",
        "relationships.approvalStep.data.id",
        "relationships.construction.data.id",
        "relationships.road.data.id",
        "relationships.firm.data.id",
        "relationships.occurrenceType.data.id",
        "relationships.subcompany.data.id",
        "relationships.construction.data.id",
        "foundAt",
        "executedAt",
        "createdAt",
        "dueAt",
        "lane",
        "track",
        "lot",
        "branch",
        "occurrenceKind",
        "direction",
        "roadName",
        "_fixedCoordinate",
        "_fixedPhotos",
    ]

    already_existed = not instance._state.adding
    custom_map_table = instance.custom_map_table

    if already_existed and custom_map_table:
        fields = instance.form_fields.get("fields", [])
        api_names = [item.get("apiName") or item.get("api_name") for item in fields]

        # Remove items that are no longer part of form_fields and are not in the whitelist
        instance.custom_map_table = [
            item
            for item in custom_map_table
            if item in api_names or item in API_NAME_WHITELIST
        ]


@receiver(post_save, sender=OccurrenceRecord)
@disable_signal_for_loaddata
def fill_search_tags_related_fields(sender, instance, created, **kwargs):
    """Ensure we always keep the OccurrenceRecord SearchTag fields updated"""

    occurrence_type = instance.occurrence_type
    level_to_data = {}
    if occurrence_type:
        level_to_data = {
            level: (str(search_tag_id), search_tag_name)
            for level, search_tag_name, search_tag_id in instance.search_tags.values_list(
                "level", "name", "uuid"
            )
        }
    if level_to_data:
        instance.record_tag_id, instance.record_tag = level_to_data.get(1, (None, None))
        instance.type_tag_id, instance.type_tag = level_to_data.get(2, (None, None))
        instance.kind_tag_id, instance.kind = level_to_data.get(3, (None, None))
        instance.subject_tag_id, instance.subject = level_to_data.get(4, (None, None))

        if instance.record_tag is not None:
            instance.record = instance.record_tag
        elif occurrence_type and occurrence_type.occurrence_kind:
            instance.record = occurrence_type.occurrence_kind
        else:
            instance.record = None

        if instance.type_tag is not None:
            instance.type = instance.type_tag
        elif occurrence_type:
            instance.type = occurrence_type.name
        else:
            instance.type = None

        with DisableSignals():
            instance.save()
