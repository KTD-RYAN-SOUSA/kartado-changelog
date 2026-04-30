import logging
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import datetime

import sentry_sdk
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import GeometryCollection, Point
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django_bulk_update.helper import bulk_update
from fieldsignals.signals import post_save_changed, pre_save_changed
from fnc.mappings import get
from rest_framework_json_api import serializers
from simple_history.signals import pre_create_historical_record
from simple_history.utils import bulk_create_with_history

from apps.occurrence_records.models import RecordPanel
from apps.reportings.helpers.default_menus import rebalance_visible_menus_orders
from apps.service_orders.models import ServiceOrderActionStatusSpecs
from apps.services.models import ServiceSpecs
from helpers.apps.ccr_report_utils.form_data import remove_old_values_in_form_data
from helpers.apps.companies import is_energy_company
from helpers.apps.json_logic import apply_json_logic
from helpers.apps.reportings import (
    get_inspections,
    update_created_recuperations_with_relation,
    update_reporting_inventory_candidates,
    update_reporting_inventory_candidates_from_inventories,
)
from helpers.apps.services import (
    create_or_update_services_and_usages,
    impact_current_balance,
    impact_measurement_balance,
)
from helpers.forms import get_topics
from helpers.histories import bulk_update_with_history
from helpers.km_converter import get_road_coordinates
from helpers.middlewares import get_current_user
from helpers.road_defaults import create_default_segment_road, should_add_default_marks
from helpers.signals import disable_signal_for_loaddata
from helpers.strings import get_autonumber_array, get_obj_from_path

from .models import (
    HistoricalReporting,
    RecordMenu,
    RecordMenuRelation,
    Reporting,
    ReportingFile,
)
from .serializers import ReportingSerializer


@receiver(pre_save, sender=Reporting)
def auto_add_reporting_number(sender, instance, **kwargs):
    if instance.number in [None, ""]:
        if instance.occurrence_type:
            try:
                occurrence_kind = instance.occurrence_type.occurrence_kind
            except Exception:
                raise serializers.ValidationError("Occurrence Kind not found!")
        else:
            occurrence_kind = ""

        key_name = "RP_name_format"
        number_format = ""

        if key_name in instance.company.metadata:
            try:
                number_format = instance.company.metadata[key_name][occurrence_kind]
            except Exception:
                if "default" in instance.company.metadata[key_name]:
                    number_format = instance.company.metadata[key_name]["default"]
                else:
                    raise serializers.ValidationError("Variáveis de nome inválidas!")
        else:
            raise serializers.ValidationError("Variáveis de nome inválidas!")

        instance_type = number_format["type"]

        # Get datetime and serial arrays
        data = get_autonumber_array(instance.company.uuid, instance_type)

        # Get company prefix
        if "company_prefix" in instance.company.metadata:
            data["prefixo"] = instance.company.metadata["company_prefix"]
        else:
            data["prefixo"] = "[{}]".format(instance.company.name)

        # Make number
        try:
            number = number_format["format"].format(**data)
        except Exception as e:
            print(e)
            # Fallback
            # UHIT-RG-2018.0001
            number = "{prefixo}-{nome}-{anoCompleto}.{serialAno}".format(**data)

        instance.number = number


@receiver(pre_save, sender=Reporting)
def reporting_create(sender, instance, **kwargs):
    if instance._state.adding:
        # fill point
        if not instance.point:
            if instance.road_name:
                instance.point, instance.road = get_road_coordinates(
                    instance.road_name,
                    instance.km,
                    instance.direction,
                    instance.company,
                ) or (Point(0, 0), None)

                # Se não encontrou road e existe road_name, cria road clone com trecho padrão
                if not instance.road and instance.road_name:
                    from apps.roads.models import Road

                    # Busca rodovias base (exclui clones is_default_segment)
                    roads = Road.objects.filter(
                        name=instance.road_name,
                        direction=int(instance.direction),
                        company=instance.company,
                        is_default_segment=False,
                    )

                    if not roads.exists():
                        # Busca sem direção específica
                        roads = Road.objects.filter(
                            name=instance.road_name,
                            company=instance.company,
                            is_default_segment=False,
                        ).order_by("direction")

                    if roads.exists():
                        # Encontrou rodovia mas o KM está fora do range
                        road = roads.first()

                        # Verifica se a rodovia não tem lot_logic e precisa de trecho padrão
                        if should_add_default_marks(road):
                            # Cria nova road clone com marcos padrão
                            new_road = create_default_segment_road(
                                road, instance.company
                            )
                            # Associa o apontamento à nova rodovia com trecho padrão
                            instance.road = new_road
                            # Recalcula o ponto com a rodovia atualizada
                            instance.point, _ = get_road_coordinates(
                                instance.road_name,
                                instance.km,
                                instance.direction,
                                instance.company,
                            ) or (instance.point, new_road)

            else:
                instance.point = Point(0, 0)
            if not instance.geometry:
                instance.geometry = GeometryCollection(instance.point)
        elif instance.point and instance.geometry:
            if instance.road_name:
                _, instance.road = get_road_coordinates(
                    instance.road_name,
                    instance.km,
                    instance.direction,
                    instance.company,
                ) or (instance.point, None)

                # Se não encontrou road e existe road_name, cria road clone com trecho padrão
                if not instance.road and instance.road_name:
                    from apps.roads.models import Road

                    # Busca rodovias base (exclui clones is_default_segment)
                    roads = Road.objects.filter(
                        name=instance.road_name,
                        direction=int(instance.direction),
                        company=instance.company,
                        is_default_segment=False,
                    )

                    if not roads.exists():
                        # Busca sem direção específica
                        roads = Road.objects.filter(
                            name=instance.road_name,
                            company=instance.company,
                            is_default_segment=False,
                        ).order_by("direction")

                    if roads.exists():
                        # Encontrou rodovia mas o KM está fora do range
                        road = roads.first()

                        # Verifica se a rodovia não tem lot_logic e precisa de trecho padrão
                        if should_add_default_marks(road):
                            # Cria nova road clone com marcos padrão
                            new_road = create_default_segment_road(
                                road, instance.company
                            )
                            # Associa o apontamento à nova rodovia com trecho padrão
                            instance.road = new_road

        try:
            executed_status_order = instance.company.metadata["executed_status_order"]
            order = (
                ServiceOrderActionStatusSpecs.objects.filter(
                    company=instance.company, status=instance.status
                )
                .first()
                .order
            )
            if order >= executed_status_order:
                if not instance.executed_at:
                    instance.executed_at = datetime.now()
        except Exception as e:
            print(e)


@receiver(post_save, sender=Reporting)
@disable_signal_for_loaddata
def check_road_name_and_point(sender, created, instance, **kwargs):
    hide_reporting_location = (
        get_obj_from_path(instance.company.metadata, "hide_reporting_location") or False
    )
    run_bulk_update = False
    if instance.road_name and not hide_reporting_location:
        km_threshold = 1

        test_point, test_road = get_road_coordinates(
            instance.road_name,
            instance.km,
            instance.direction,
            instance.company,
        ) or (Point(0, 0), None)

        distance_in_km = (
            instance.point.distance(test_point) * 100
            if instance.point
            else km_threshold
        )

        if (
            (instance.road and instance.road_name != instance.road.name)
            or (distance_in_km >= km_threshold)
        ) and test_road:
            if not instance.geometry:
                instance.point = test_point
                instance.geometry = GeometryCollection(test_point)
                run_bulk_update = True

            if not instance.road or instance.road != test_road:
                instance.road = test_road
                run_bulk_update = True

            if test_road.lot_logic and test_road.lot_logic != {}:
                try:
                    result = apply_json_logic(
                        instance.road.lot_logic, {"data": {"km": instance.km}}
                    )
                except Exception:
                    result = ""
            else:
                result = None
            if not instance.lot or instance.lot != result:
                instance.lot = result
                run_bulk_update = True

            if test_road.city_logic and test_road.city_logic != {}:
                try:
                    city_result = apply_json_logic(
                        instance.road.city_logic, {"data": {"km": instance.km}}
                    )
                except Exception:
                    city_result = ""
            else:
                city_result = None
            if not instance.city or instance.city != city_result:
                instance.city = city_result
                run_bulk_update = True

            if run_bulk_update:
                bulk_update_with_history(
                    objs=[instance],
                    model=Reporting,
                    user=None,
                    use_django_bulk=True,
                )
        if not instance.road and test_road:
            # This will only be called on ExcelImport and if the manual point is
            # less than 1km from the point where the instance.km is located in the road
            instance.road = test_road
            if not instance.geometry:
                instance.geometry = (
                    GeometryCollection(instance.point)
                    if instance.point
                    else GeometryCollection(test_point)
                )

            if test_road.lot_logic and test_road.lot_logic != {}:
                try:
                    result = apply_json_logic(
                        instance.road.lot_logic, {"data": {"km": instance.km}}
                    )
                except Exception:
                    result = ""
            else:
                result = None
            instance.lot = result

            if test_road.city_logic and test_road.city_logic != {}:
                try:
                    city_result = apply_json_logic(
                        instance.road.city_logic, {"data": {"km": instance.km}}
                    )
                except Exception:
                    city_result = ""
            else:
                city_result = ""
            instance.city = city_result or ""

            bulk_update_with_history(
                objs=[instance],
                model=Reporting,
                user=None,
                use_django_bulk=True,
            )

    if hide_reporting_location:
        if not instance.geometry:
            if instance.point:
                instance.geometry = GeometryCollection(instance.point)
        else:
            instance.point = instance.geometry.centroid
        bulk_update_with_history(
            objs=[instance],
            model=Reporting,
            user=None,
            use_django_bulk=True,
        )


@receiver(post_save, sender=Reporting)
def fill_geometry_if_none(sender, created, instance, **kwargs):
    if instance.point is None or instance.geometry is None:
        if instance.point is None:
            instance.point = Point(0, 0)

        if instance.geometry is None:
            instance.geometry = GeometryCollection(instance.point)

        bulk_update_with_history(
            objs=[instance],
            model=Reporting,
            user=None,
            use_django_bulk=True,
        )


@receiver(pre_save_changed, sender=Reporting)
def reporting_update(sender, instance, changed_fields, **kwargs):
    if not instance.pk:
        return
    if not instance._state.adding:
        field_names = [a for a in changed_fields.keys()]
        changed_items = list(changed_fields.items())
        if "geometry" in field_names:
            geometry = next((a, b) for a, b in changed_items if a == "geometry")
            changed_items.insert(0, changed_items.pop(changed_items.index(geometry)))
        # MAKE SURE 'STATUS' IS THE FIRST TO RUN
        if "status" in field_names:
            status = next((a, b) for a, b in changed_items if a == "status")
            changed_items.insert(0, changed_items.pop(changed_items.index(status)))
        for field, (old, new) in changed_items:
            if field == "km" or field == "road_name":
                if instance.road_name:
                    temp_point, instance.road = get_road_coordinates(
                        instance.road_name,
                        instance.km,
                        instance.direction,
                        instance.company,
                    )

                    # Se não encontrou road e existe road_name, cria road clone com trecho padrão
                    if not instance.road and instance.road_name:
                        from apps.roads.models import Road

                        # Busca rodovias base (exclui clones is_default_segment)
                        roads = Road.objects.filter(
                            name=instance.road_name,
                            direction=int(instance.direction),
                            company=instance.company,
                            is_default_segment=False,
                        )

                        if not roads.exists():
                            # Busca sem direção específica
                            roads = Road.objects.filter(
                                name=instance.road_name,
                                company=instance.company,
                                is_default_segment=False,
                            ).order_by("direction")

                        if roads.exists():
                            # Encontrou rodovia mas o KM está fora do range
                            road = roads.first()

                            # Verifica se a rodovia não tem lot_logic e precisa de trecho padrão
                            if should_add_default_marks(road):
                                # Cria nova road clone com marcos padrão
                                new_road = create_default_segment_road(
                                    road, instance.company
                                )
                                # Associa o apontamento à nova rodovia com trecho padrão
                                instance.road = new_road
                                # Recalcula o ponto com a rodovia atualizada
                                temp_point, _ = get_road_coordinates(
                                    instance.road_name,
                                    instance.km,
                                    instance.direction,
                                    instance.company,
                                ) or (temp_point, new_road)

                        # Se ainda não encontrou road, verifica se existe clone de trecho
                        # padrão para manter o vínculo (km fora do range da rodovia real)
                        if not instance.road and instance.road_name:
                            existing_clone = Road.objects.filter(
                                name=instance.road_name,
                                direction=int(instance.direction),
                                company=instance.company,
                                is_default_segment=True,
                            ).first()

                            if not existing_clone:
                                existing_clone = (
                                    Road.objects.filter(
                                        name=instance.road_name,
                                        company=instance.company,
                                        is_default_segment=True,
                                    )
                                    .order_by("direction")
                                    .first()
                                )

                            if existing_clone:
                                instance.road = existing_clone

                if "geometry" not in field_names and not instance.manual_geometry:
                    instance.point = temp_point
                    instance.geometry = GeometryCollection(instance.point)
            if field == "geometry":
                if new != old:
                    instance.point = (
                        instance.geometry.centroid if instance.geometry else None
                    )
                if not new:
                    instance.manual_geometry = False
                else:
                    instance.manual_geometry = True

            if field == "status":
                statuses = sender.status.get_queryset()
                try:
                    old_status = next(a for a in statuses if a.pk == old)
                    new_status = next(a for a in statuses if a.pk == new)
                except StopIteration:
                    continue

                try:
                    old_order = (
                        ServiceOrderActionStatusSpecs.objects.filter(
                            company=instance.company, status=old_status
                        )
                        .first()
                        .order
                    )

                    new_order = (
                        ServiceOrderActionStatusSpecs.objects.filter(
                            company=instance.company, status=new_status
                        )
                        .first()
                        .order
                    )
                except Exception:
                    continue

                try:
                    executed_status_order = instance.company.metadata[
                        "executed_status_order"
                    ]
                    if (
                        old_order < executed_status_order
                        and new_order >= executed_status_order
                    ):
                        impact_current_balance(instance)
                        # try fill executed_at if null
                        if not instance.executed_at:
                            instance.executed_at = datetime.now()
                    elif (
                        old_order >= executed_status_order
                        and new_order < executed_status_order
                    ):
                        impact_current_balance(instance, increase=True)
                        # clean executed_at
                        instance.executed_at = None
                except Exception as e:
                    print(e)
            if (
                field == "km" or field == "form_data"
            ) and "occurrence_type" not in field_names:
                create_or_update_services_and_usages(instance)
            if field == "occurrence_type":
                if len(instance.reporting_usage.all()):
                    measurement = instance.reporting_usage.all()[0].measurement
                else:
                    measurement = None
                if measurement:
                    impact_measurement_balance(instance, increase=True)
                executed_status_order = instance.company.metadata[
                    "executed_status_order"
                ]

                try:
                    instance_order = (
                        ServiceOrderActionStatusSpecs.objects.filter(
                            company=instance.company, status=instance.status
                        )
                        .first()
                        .order
                    )
                except Exception:
                    instance_order = None

                if instance_order and instance_order >= executed_status_order:
                    impact_current_balance(instance, increase=True)
                instance.reporting_usage.all().delete()
                create_or_update_services_and_usages(instance, update=False)
                if measurement:
                    create_or_update_services_and_usages(measurement, [instance])


@receiver(post_save, sender=Reporting)
def create_service_usage_objects(sender, created, instance, **kwargs):
    exists_service_specs = ServiceSpecs.objects.filter(
        occurrence_type=instance.occurrence_type,
        service__company=instance.company,
    ).exists()
    if created and exists_service_specs:
        queryset = Reporting.objects.filter(pk=instance.pk)
        reporting_class = ReportingSerializer()

        if queryset:
            if hasattr(reporting_class, "_SELECT_RELATED_FIELDS"):
                queryset = queryset.select_related(
                    *reporting_class._SELECT_RELATED_FIELDS
                )
            if hasattr(reporting_class, "_PREFETCH_RELATED_FIELDS"):
                queryset = queryset.prefetch_related(
                    *reporting_class._PREFETCH_RELATED_FIELDS
                )
            instance = queryset[0]

        create_or_update_services_and_usages(instance, update=False)


@receiver(pre_save, sender=Reporting)
@disable_signal_for_loaddata
def fill_lot_field(sender, instance, **kwargs):
    if instance.road and instance.road.lot_logic:
        # Goal 1 - Check if this Reporting occurrence_type is one of inspect_types
        inspect_types = get("metadata.csp.inspect_types", instance.company, default=[])
        if str(instance.occurrence_type.pk) in inspect_types:
            lots = {}
            all_systems = []
            lots_dict = defaultdict(list)
            metadata_topics = get("metadata.csp.topics", instance.company, default={})

            # Get inspected topics and its subclasses. Ex:
            # topics = {'5.1': ['ICRP', 'ICRFD', 'ICRDCV'], '8.1': ['IICSV'], '8.2': ['IICSH']}
            topics = get_topics(
                instance.occurrence_type.form_fields,
                instance.form_data,
                names=False,
            )

            # Get the logic to find out the road system
            system_logic = instance.road.lane_type_logic.get("system_logic", {})

            # Get inspected segments
            max_km = int(max([instance.km, instance.end_km]) + 1)
            min_km = int(min([instance.km, instance.end_km]))
            kms_list = [item for item in range(min_km, max_km + 1, 1)]

            # Find out the lot and system for each km in kms_list
            for km in kms_list:
                lot = apply_json_logic(instance.road.lot_logic, {"data": {"km": km}})
                if lot:
                    lots_dict[lot].append(km)
                if system_logic:
                    system = apply_json_logic(system_logic, {"data": {"km": km}})
                    if system:
                        all_systems.append(system)

            # Find out the count of segments for each lot and each topic
            for lot, kms in lots_dict.items():
                topics_dict = {}
                for topic, value in topics.items():
                    if topic in metadata_topics:
                        topic_type = metadata_topics[topic].get("type", "")
                        if topic_type == "segment":
                            segments = len(kms)
                        elif topic_type == "lane_segment":
                            if (
                                instance.road.lane_type_logic
                                and "type_logic" in instance.road.lane_type_logic
                            ):
                                count = 0
                                for km in kms:
                                    lane_type = apply_json_logic(
                                        instance.road.lane_type_logic["type_logic"],
                                        {"km": km},
                                    )
                                    count += int(lane_type) if lane_type else 0
                                segments = count
                            else:
                                segments = len(kms)
                        elif topic_type == "inventory":
                            segments = None
                        else:
                            segments = 0

                        for item in value:
                            topics_dict[item] = segments
                lots[lot] = {
                    "kms": kms,
                    "road": instance.road_name if instance.road_name else "",
                    "topics": topics_dict,
                }

            instance.form_data["lots"] = lots
            instance.form_data["road_system"] = (
                list(set(all_systems))[0] if all_systems else ""
            )

        # Goal 2 - Find out the lot

        try:
            result = apply_json_logic(
                instance.road.lot_logic, {"data": {"km": instance.km}}
            )
        except Exception:
            result = ""
        instance.lot = result

    if instance.road and instance.road.city_logic:
        try:
            city_result = apply_json_logic(
                instance.road.city_logic, {"data": {"km": instance.km}}
            )
        except Exception:
            city_result = ""
        instance.city = city_result


@receiver(pre_delete, sender=Reporting)
def fix_balances_on_delete(sender, instance, **kwargs):
    impact_measurement_balance(instance, increase=True)
    executed_status_order = instance.company.metadata["executed_status_order"]
    if not instance.status and instance.occurrence_type.occurrence_kind == "2":
        return

    try:
        instance_order = (
            ServiceOrderActionStatusSpecs.objects.filter(
                company=instance.company, status=instance.status
            )
            .first()
            .order
        )
    except Exception:
        raise serializers.ValidationError("Ordem não encontrada")

    if instance.status and instance_order >= executed_status_order:
        impact_current_balance(instance, increase=True)


@receiver(pre_create_historical_record, sender=HistoricalReporting)
def save_mobile_sync_in_history(sender, instance, history_instance, **kwargs):
    try:
        history_instance.mobile_sync = instance.mobile_sync
    except Exception:
        pass


@receiver(post_save, sender=RecordMenu)
def create_record_panel(sender, created, instance: RecordMenu, **kwargs):
    company = instance.company

    if created and not instance.system_default and not is_energy_company(company):
        content_type = ContentType.objects.get(
            app_label="reportings", model="reporting"
        )
        RecordPanel.objects.create(
            name="Todos",
            panel_type="LIST",
            conditions=dict(),
            list_columns=None,
            company=company,
            content_type=content_type,
            system_default=True,
            menu=instance,
        )


@receiver(post_save, sender=RecordMenuRelation)
def rebalance_after_relation_change(sender, created, instance, **kwargs):
    rebalance_visible_menus_orders(str(instance.user.pk), str(instance.company.pk))


@receiver(post_save, sender=Reporting)
@disable_signal_for_loaddata
def set_altimetry(sender, instance, created, **kwargs):
    altimetry_enable = instance.company.metadata.get("altimetry_enable", False)
    if created and altimetry_enable:
        try:
            instance.set_altimetry()
        except Exception:
            pass


@receiver(post_save_changed, sender=Reporting)
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


@receiver(post_delete, sender=Reporting)
def update_created_recuperations_with_relation_on_delete(sender, instance, **kwargs):
    try:
        if instance.company:
            inspections = get_inspections([instance], instance.company)
            if inspections:
                update_created_recuperations_with_relation(
                    inspections, instance.company
                )
    except Exception as e:
        sentry_sdk.capture_exception(e)


@receiver(post_delete, sender=ReportingFile)
def remove_old_values_after_delete_file(sender, instance, **kwargs):
    try:
        reporting = getattr(instance, "reporting")
        if reporting is None:
            return

        target = str(instance.pk)
        form_data = reporting.form_data
        remove_old_values_in_form_data(form_data, target)
        reporting.form_data = form_data
        bulk_update_with_history(
            objs=[reporting],
            model=Reporting,
            user=None,
            use_django_bulk=True,
        )
    except Exception as err:
        print(
            ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> remove_old_values_after_delete_file", err
        )


@receiver(post_save, sender=Reporting)
def add_last_monitoring_files(sender, instance: Reporting, created: bool, **kwargs):
    if not created:
        return
    request_user = get_current_user()
    try:
        company = instance.company
        metadata = getattr(company, "metadata", {})
        inspection_kind = get_obj_from_path(metadata, "inspection_occurrence_kind")

        if isinstance(inspection_kind, str):
            inspection_kind = [inspection_kind]

        monitoring_ids = set(str(x) for x in inspection_kind)

        occ = instance.occurrence_type
        if not occ or str(occ.occurrence_kind) not in monitoring_ids:
            return

        inv = getattr(instance, "parent", None)
        if inv is None:
            return

        last_monitoring = (
            inv.children.exclude(uuid=instance.uuid)
            .filter(occurrence_type=occ)
            .order_by("-found_at")
            .all()
        )
        if not last_monitoring:
            return
        last_monitoring = last_monitoring[0]

        last_monitoring_list = last_monitoring.form_data.get("last_monitoring", [])
        ignore_files_uuids = set()
        for item in last_monitoring_list:
            if isinstance(item, dict) and "last_monitoring_files" in item:
                ignore_files_uuids.update(
                    str(uuid) for uuid in item["last_monitoring_files"]
                )

        uuid_cloned = []
        created_reporting_files = []
        files = last_monitoring.reporting_files.all()
        for rf in files:
            if str(rf.uuid) in ignore_files_uuids:
                continue
            new_rf = deepcopy(rf)
            new_rf.uuid = uuid.uuid4()
            new_rf.reporting = instance
            new_rf.is_shared = False
            new_rf.include_dnit = True
            new_rf.created_by = request_user
            created_reporting_files.append(new_rf)
            uuid_cloned.append(str(new_rf.uuid))

        bulk_create_with_history(
            created_reporting_files, ReportingFile, default_user=request_user
        )

        if uuid_cloned:
            fd = dict(instance.form_data or {})
            fd["last_monitoring"] = [{"last_monitoring_files": uuid_cloned}]
            instance.form_data = fd
            bulk_update([instance], update_fields=["form_data"])
    except Exception as e:
        logging.warning(f"Error copying last monitoring files: {str(e)}")


@receiver(post_save, sender=Reporting)
@disable_signal_for_loaddata
def update_reporting_inventory_candidates_on_save(sender, instance, **kwargs):
    """
    Signal handler to update inventory candidates after a Reporting is saved.
    """
    # Check if reporting is not an inventory (occurrence_kind != "2")
    if instance.occurrence_type and instance.occurrence_type.occurrence_kind != "2":
        try:
            update_reporting_inventory_candidates([instance], instance.company)
        except Exception as e:
            logging.warning(
                f"Error updating inventory candidates for reporting {instance.uuid}: {str(e)}"
            )
    else:
        try:
            update_reporting_inventory_candidates_from_inventories(
                [instance], instance.company
            )
        except Exception as e:
            logging.warning(
                f"Error updating inventory candidates for inventory {instance.uuid}: {str(e)}"
            )


@receiver(post_save, sender=Reporting)
@disable_signal_for_loaddata
def auto_schedule_reporting(sender, created, instance, **kwargs):
    if created:
        from helpers.apps.auto_scheduling import process_auto_scheduling

        process_auto_scheduling(instance)
