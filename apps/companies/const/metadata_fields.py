from typing import Dict

# Accepted fields and their respective expected types
METADATA_FIELD_TO_TYPE: Dict[str, type] = {
    "use_custom_reporting_fields": bool,
    "custom_reporting_fields": list,
    "use_custom_inventory_fields": bool,
    "custom_inventory_fields": list,
    "field_to_automatically_link_reportings_to_rdo": str,
    "use_custom_occurrence_record_fields": bool,
    "custom_occurrence_record_fields": list,
    "altimetry_enable": bool,
    "inventory_field_in_reporting": bool,
    "show_coordinate_input": bool,
    "use_reporting_inventory_dashboard_shape_list": bool,
    "toggle_dashboard_new_shape_update": bool,
    "copy_occurrences_to_new_rdo": bool,
    "company_mapping": list,
    "app_max_zoom_level": int,
    "auto_archive_completed_jobs": bool,
    "consider_approval_for_job_progress": bool,
}
