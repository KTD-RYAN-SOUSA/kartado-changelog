from rest_framework_json_api import serializers

from helpers.strings import get_obj_from_path


def get_subphase_percentage_done(
    progress_details, phase_index: int, subphase_index: int, subphase
):
    related_progress_details = [
        detail
        for detail in progress_details
        if int(detail["phase"]) == phase_index
        and int(detail["subphase"]) == subphase_index
    ]
    executed_amount = sum(
        [
            get_obj_from_path(detail, "executedAmount")
            for detail in related_progress_details
        ]
    )

    subphase_expected_amount = get_obj_from_path(subphase, "expectedAmount")

    if subphase_expected_amount <= 0:
        raise serializers.ValidationError(
            "kartado.error.construction.subphase_has_zero_or_negative_expected_amount"
        )
    return round(executed_amount / subphase_expected_amount, 2)


def get_phase_percentage_done(subphase_total, subphase_quantity):
    return subphase_total / subphase_quantity if subphase_quantity > 0 else 0.0


def get_percentage_done(construction_progress):
    total_phase_percentage_done = 0.0
    phase_quantity = 0
    for phase_index, phase in enumerate(construction_progress.construction.phases):
        subphase_total = 0.0
        subphase_quantity = 0
        for subphase_index, subphase in enumerate(
            get_obj_from_path(phase, "subphases")
        ):

            subphase_total += get_subphase_percentage_done(
                phase_index=phase_index,
                subphase_index=subphase_index,
                subphase=subphase,
                progress_details=construction_progress.progress_details,
            )
            subphase_quantity += 1
        total_phase_percentage_done += get_phase_percentage_done(
            subphase_total=subphase_total,
            subphase_quantity=subphase_quantity,
        )
        phase_quantity += 1

    return total_phase_percentage_done / phase_quantity if phase_quantity > 0 else 0.0
