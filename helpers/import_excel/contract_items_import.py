import json
import logging

from django.core.files.base import ContentFile

from apps.templates.models import ExcelImport
from apps.users.models import User
from helpers.apps.contract_utils import calculate_contract_prices
from helpers.import_excel.contract_item_administration_import import (
    ImportContractItemAdministration,
)
from helpers.import_excel.contract_item_administration_import import (
    create_contract_items_from_preview as create_admin_items_from_preview,
)
from helpers.import_excel.contract_item_unit_price_import import (
    ImportContractItemUnitPrice,
    create_contract_items_from_preview,
)


def generate_preview(excel_import_id, user_id):
    """
    Processes Excel files containing both unit_price and administration sheets
    """
    excel_import = None
    try:
        excel_import = ExcelImport.objects.get(pk=excel_import_id)
        user = User.objects.get(pk=user_id)

        unit_price_importer = ImportContractItemUnitPrice(excel_import, user)
        admin_importer = ImportContractItemAdministration(excel_import, user)

        unit_price_success = unit_price_importer.process_excel()
        admin_success = admin_importer.process_excel()

        combined_data = {}

        unit_price_data = unit_price_importer.get_preview_data()
        combined_data["contract_items_unit_price"] = unit_price_data.get(
            "contract_items_unit_price", []
        )
        if not combined_data.get("contract_id"):
            combined_data["contract_id"] = unit_price_data.get("contract_id")
        if not combined_data.get("contract_summary"):
            combined_data["contract_summary"] = unit_price_data.get("contract_summary")

        admin_data = admin_importer.get_preview_data()
        combined_data["contract_items_administration"] = admin_data.get(
            "contract_items_administration", []
        )
        if not combined_data.get("contract_id"):
            combined_data["contract_id"] = admin_data.get("contract_id")
        if not combined_data.get("contract_summary"):
            combined_data["contract_summary"] = admin_data.get("contract_summary")

        json_data = json.dumps(combined_data)
        excel_import.preview_file.save(
            f"{excel_import.uuid}.json", ContentFile(json_data.encode("utf-8"))
        )

        excel_import.generating_preview = False
        excel_import.error = not (unit_price_success and admin_success)
        excel_import.save()
        return excel_import

    except Exception as e:
        logging.error(f"Error in generate_preview: {str(e)}")
        if excel_import:
            excel_import.generating_preview = False
            excel_import.error = True
            excel_import.save()
        return None


def execute_import(excel_import_id):
    """
    Executes import containing both unit_price and administration items
    """
    excel_import = None
    try:
        excel_import = ExcelImport.objects.get(pk=excel_import_id)
        if excel_import.done:
            return True

        if excel_import.error:
            return False

        if excel_import.preview_file:
            preview_content = excel_import.preview_file.read()
            preview_data = json.loads(preview_content)

            if (
                isinstance(preview_data, dict)
                and "contract_id" in preview_data
                and (
                    "contract_items_unit_price" in preview_data
                    or "contract_items_administration" in preview_data
                )
            ):
                unit_price_success = True
                admin_success = True

                if preview_data.get("contract_items_unit_price"):
                    importer = ImportContractItemUnitPrice(
                        excel_import, excel_import.created_by
                    )
                    unit_price_success = create_contract_items_from_preview(
                        importer, preview_data
                    )

                if preview_data.get("contract_items_administration"):
                    admin_importer = ImportContractItemAdministration(
                        excel_import, excel_import.created_by
                    )
                    admin_success = create_admin_items_from_preview(
                        admin_importer, preview_data
                    )

                if unit_price_success or admin_success:
                    contract_id = preview_data.get("contract_id")
                    if contract_id:
                        calculate_contract_prices(contract_id)

                excel_import.generating_preview = False
                excel_import.done = True
                excel_import.error = not (unit_price_success and admin_success)
                excel_import.save()

                return unit_price_success and admin_success

        excel_import.error = True
        excel_import.save()
        return False
    except Exception as e:
        logging.error(f"Error in execute_import: {str(e)}")
        if excel_import:
            excel_import.error = True
            excel_import.save()
        return False
