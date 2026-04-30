from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from apps.roads.models import Road
from helpers.road_defaults import reassociate_clone_reportings
from helpers.route_maker import Router
from RoadLabsAPI.settings.credentials import GMAPS_API_KEY, MAPBOX_API_KEY


@receiver(pre_save, sender=Road)
def calculate_route(sender, instance, **kwargs):
    route = Router(GMAPS_API_KEY, MAPBOX_API_KEY, instance.manual_road)
    route.set_marks(instance.marks)
    route.make_route()

    instance.path = route.path
    instance.length = route.length
    instance.marks = route.dict_mark
    instance.all_marks_have_indexes = all(
        ["index" in mark for mark in instance.marks.values()]
    )


@receiver(m2m_changed, sender=Road.company.through)
def update_city_logic_in_roads(sender, instance, action, **kwargs):
    if action == "post_add":
        roads = (
            Road.objects.filter(name=instance.name, company__in=instance.company.all())
            .exclude(pk=instance.pk)
            .distinct()
        )

        if instance.city_logic:
            roads.update(city_logic=instance.city_logic)

        if not instance.city_logic and getattr(instance, "created_flag", False):
            roads_with_city_logic = roads.exclude(city_logic={})
            if roads_with_city_logic.exists():
                Road.objects.filter(pk=instance.pk).update(
                    city_logic=roads_with_city_logic[0].city_logic
                )


@receiver(m2m_changed, sender=Road.company.through)
def update_lot_logic_in_roads(sender, instance, action, **kwargs):
    # Company is mandatory to create Roads, so this signal
    # will be always called on create and it will be called
    # on updates if the companies have changed
    if action == "post_add":
        roads = (
            Road.objects.filter(name=instance.name, company__in=instance.company.all())
            .exclude(pk=instance.pk)
            .distinct()
        )

        if instance.lot_logic:
            roads.update(lot_logic=instance.lot_logic)

        if not instance.lot_logic and getattr(instance, "created_flag", False):
            roads_with_lot_logic = roads.exclude(lot_logic={})
            if roads_with_lot_logic.exists():
                Road.objects.filter(pk=instance.pk).update(
                    lot_logic=roads_with_lot_logic[0].lot_logic
                )


@receiver(post_save, sender=Road)
def helper_update_lot_logic(sender, instance, created, **kwargs):
    # Use this signal to pass the flag to m2m_changed signal
    instance.created_flag = created


@receiver(post_save, sender=Road)
def reassociate_reportings_after_lot_logic(sender, instance, **kwargs):
    if instance.lot_logic and instance.lot_logic != {}:
        reassociate_clone_reportings(instance)


@receiver(pre_save, sender=Road)
def update_city_logic_on_update(sender, instance, **kwargs):
    if not instance._state.adding:
        roads = (
            Road.objects.filter(name=instance.name, company__in=instance.company.all())
            .exclude(pk=instance.pk)
            .distinct()
        )

        if instance.city_logic:
            roads.update(city_logic=instance.city_logic)


@receiver(pre_save, sender=Road)
def update_lot_logic_on_update(sender, instance, **kwargs):
    # This code will run just on updates
    if not instance._state.adding:
        roads = (
            Road.objects.filter(name=instance.name, company__in=instance.company.all())
            .exclude(pk=instance.pk)
            .distinct()
        )

        if instance.lot_logic:
            roads.update(lot_logic=instance.lot_logic)
