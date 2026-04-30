import json
import logging
import uuid

import sentry_sdk
from django.core.files.base import ContentFile
from django.db.models import Max

from apps.companies.models import Entity
from apps.resources.models import (
    Contract,
    ContractItemUnitPrice,
    ContractService,
    Resource,
)
from apps.service_orders.models import AdditionalControl, ServiceOrderResource
from apps.templates.models import ExcelContractItemUnitPrice, ExcelImport
from apps.templates.serializers import ExcelContractItemUnitPriceSerializer
from apps.users.models import User
from helpers.apps.contract_utils import calculate_contract_prices
from helpers.import_excel.shared_functions import (
    shared_clean_up,
    shared_download_excel_file,
    shared_is_hidden_sheet,
    shared_load_data,
    shared_update_column_errors,
)
from helpers.permissions import PermissionManager
from helpers.strings import clean_latin_string


class ImportContractItemUnitPrice:
    """
    Class responsible for handling the import of ContractItemUnitPrice objects from Excel
    """

    temp_path = "/tmp/contract_item_excel_import/"

    REQUIRED_FIELDS = [
        "secao de preco unitario",
        "codigo",
        "recurso",
        "quantidade",
        "formato de medicao",
        "valor unitario",
    ]

    COLUMN_NAME_MAPPING = {
        "section_name": "Seção de Preço Unitário",
        "sort_string": "Código",
        "resource_name": "Recurso",
        "entity_name": "Entidade",
        "amount": "Quantidade",
        "unit": "Formato de Medição",
        "unit_price": "Valor Unitário",
        "additional_control": "Controle Adicional",
    }

    def __init__(self, excel_import, user):
        self.excel_import = excel_import
        self.user = user
        self.company = excel_import.company
        self.company_id = str(excel_import.company_id)
        self.user_id = str(user.uuid)
        self.contract = None
        self.contract_id = None
        self.file_name = ""
        self.created_contract_items_unit_price = []
        self.preview_contract_items_unit_price = []
        self.errors = []

    def download_excel_file(self):
        return shared_download_excel_file(self.excel_import, self.temp_path)

    def load_data(self):
        self.wb = shared_load_data(self.file_name, use_openpyxl=True)

    def process_info_sheet(self):
        for sheet in self.wb.worksheets:
            if not shared_is_hidden_sheet(sheet):
                continue

            values = list(sheet.values)
            if not values or len(values) < 2:
                continue

            header = {
                clean_latin_string(str(col)).lower().strip(): idx
                for idx, col in enumerate(values[0])
                if col
            }
            idx = header.get("identificador do objeto")
            if idx is not None and idx < len(values[1]) and values[1][idx]:
                try:
                    self.contract = Contract.objects.get(uuid=values[1][idx])
                    self.contract_id = str(values[1][idx])
                    return True
                except Exception:
                    return False
        return False

    def update_column_errors(self, item_dict, column_errors):
        return shared_update_column_errors(
            item_dict, column_errors, self.COLUMN_NAME_MAPPING
        )

    def find_items_sheet(self):
        for sheet in self.wb.worksheets:
            sheet_values = list(sheet.values)
            if not sheet_values:
                continue

            header = sheet_values[0]
            header_map = {}
            for idx, col in enumerate(header):
                if not col:
                    continue

                col_text = clean_latin_string(str(col)).lower().strip()
                header_map[col_text] = idx

                if " de " in col_text:
                    col_without_de = col_text.replace(" de ", " ")
                    header_map[col_without_de] = idx

                col_without_spaces = col_text.replace(" ", "")
                header_map[col_without_spaces] = idx

            missing_fields = []

            permissions = PermissionManager(
                user=self.user, company_ids=self.company, model="Entity"
            )
            self.can_view_entity = permissions.has_permission(permission="can_view")
            if self.can_view_entity:
                self.REQUIRED_FIELDS.append("entidade")

            for required_field in self.REQUIRED_FIELDS:
                field_norm = required_field.lower().strip()
                field_without_spaces = field_norm.replace(" ", "")

                if field_norm in header_map or field_without_spaces in header_map:
                    continue

                found = False
                for header_key in header_map.keys():
                    if field_norm in header_key or header_key in field_norm:
                        header_map[field_norm] = header_map[header_key]
                        found = True
                        break

                if not found:
                    missing_fields.append(required_field)

            if not missing_fields:
                return sheet, header_map
        return None, None

    def process_items_sheet(self):
        try:
            contract_items_unit_price_sheet, header_map = self.find_items_sheet()
            if not contract_items_unit_price_sheet or not header_map:
                return False

            section_idx = header_map.get("secao de preco unitario")
            code_idx = header_map.get("codigo")
            resource_idx = header_map.get("recurso")
            entity_idx = header_map.get("entidade")
            control_idx = header_map.get("controle adicional", None)
            amount_idx = header_map.get("quantidade")
            unit_price_idx = header_map.get("valor unitario")
            unit_idx = header_map.get("formato de medicao")

            data_rows = list(contract_items_unit_price_sheet.values)[1:]
            data_rows_count = 0
            for row_idx, row in enumerate(data_rows, 2):
                has_data = False

                for idx in [
                    section_idx,
                    code_idx,
                    resource_idx,
                    entity_idx,
                    control_idx,
                    amount_idx,
                    unit_price_idx,
                    unit_idx,
                ]:
                    if idx is not None and idx < len(row) and row[idx]:
                        value = row[idx]
                        if value is not None and str(value).strip():
                            has_data = True
                            break

                if not has_data:
                    continue

                data_rows_count += 1
                item_dict = {"row": row_idx, "column_errors": []}

                section_name = (
                    row[section_idx]
                    if section_idx is not None and section_idx < len(row)
                    else ""
                )
                sort_string = (
                    row[code_idx]
                    if code_idx is not None and code_idx < len(row)
                    else ""
                )
                resource_name = (
                    row[resource_idx]
                    if resource_idx is not None and resource_idx < len(row)
                    else ""
                )
                entity_name = (
                    row[entity_idx]
                    if entity_idx is not None and entity_idx < len(row)
                    else ""
                )
                additional_control = (
                    row[control_idx]
                    if control_idx is not None and control_idx < len(row)
                    else None
                )

                try:
                    amount = (
                        float(row[amount_idx])
                        if amount_idx is not None
                        and amount_idx < len(row)
                        and row[amount_idx] is not None
                        else 0
                    )
                except (ValueError, TypeError):
                    amount = 0
                    item_dict["amount_error"] = {
                        "error": "Quantidade deve ser um valor numérico maior que zero"
                    }

                try:
                    unit_price = (
                        float(row[unit_price_idx])
                        if unit_price_idx is not None
                        and unit_price_idx < len(row)
                        and row[unit_price_idx] is not None
                        else 0
                    )
                except (ValueError, TypeError):
                    unit_price = 0
                    item_dict["unit_price_error"] = {
                        "error": "Valor Unitário deve ser um valor numérico maior que zero"
                    }

                unit = (
                    row[unit_idx]
                    if unit_idx is not None and unit_idx < len(row)
                    else ""
                )

                item_dict["section_name"] = section_name
                item_dict["sort_string"] = sort_string
                item_dict["resource_name"] = resource_name
                item_dict["entity_name"] = entity_name
                item_dict["additional_control"] = additional_control
                item_dict["amount"] = amount
                item_dict["unit_price"] = unit_price
                item_dict["unit"] = unit

                column_errors = []
                if not sort_string:
                    column_errors.append("sort_string")
                if not resource_name:
                    column_errors.append("resource_name")
                if amount <= 0:
                    column_errors.append("amount")
                if unit_price <= 0:
                    column_errors.append("unit_price")
                if not unit:
                    column_errors.append("unit")

                if entity_name:
                    entity = Entity.objects.filter(
                        company=self.company,
                        name=str(entity_name).strip(),
                    ).first()
                else:
                    entity = None

                if section_name:
                    section = ContractService.objects.filter(
                        description=str(section_name).strip(),
                        firms__company=self.company,
                        unit_price_service_contracts__uuid=self.contract_id,
                    ).first()
                else:
                    section = None

                additional_control_obj = None
                if additional_control:
                    additional_control_obj = AdditionalControl.objects.filter(
                        company=self.company,
                        name=str(additional_control).strip(),
                        is_active=True,
                    ).first()

                if entity_name or self.can_view_entity:
                    if not entity:
                        item_dict["entity_error"] = {"error": "Entidade não encontrada"}
                        column_errors.append("entity_name")

                if not section:
                    item_dict["section_error"] = {
                        "error": "Seção de preço unitário não encontrada"
                    }
                    column_errors.append("section_name")

                if additional_control and not additional_control_obj:
                    item_dict["additional_control_error"] = {
                        "error": "Controle adicional não encontrado"
                    }
                    column_errors.append("additional_control")

                item_dict = self.update_column_errors(item_dict, column_errors)
                self.preview_contract_items_unit_price.append(item_dict)

            return len(self.preview_contract_items_unit_price) > 0
        except Exception as e:
            logging.error(f"Error in process_items_sheet: {str(e)}")
            return False

    def get_contract_summary(self):
        contract_summary = {
            "number": self.contract.extra_info.get("r_c_number")
            if self.contract
            else None,
            "subcompany_name": self.contract.subcompany.name
            if self.contract and self.contract.subcompany
            else None,
            "name": self.contract.name if self.contract else None,
            "contract_start": self.contract.contract_start.isoformat()
            if self.contract and self.contract.contract_start
            else None,
            "contract_end": self.contract.contract_end.isoformat()
            if self.contract and self.contract.contract_end
            else None,
            "accounting_classification": self.contract.extra_info.get(
                "accounting_classification"
            )
            if self.contract
            else None,
            "status_name": self.contract.status.name
            if self.contract and self.contract.status
            else None,
            "performance_months": self.contract.performance_months
            if self.contract
            else None,
        }

        return contract_summary

    def get_preview_data(self):
        preview_data = {
            "contract_id": self.contract_id,
            "contract_items_unit_price": [],
            "contract_summary": self.get_contract_summary(),
        }

        if self.preview_contract_items_unit_price:
            for item in self.preview_contract_items_unit_price:
                item_data = {
                    "sort_string": item.get("sort_string", ""),
                    "resource_name": item.get("resource_name", ""),
                    "entity_name": item.get("entity_name", ""),
                    "amount": item.get("amount", 0),
                    "unit_price": item.get("unit_price", 0),
                    "section_name": item.get("section_name", ""),
                    "unit": item.get("unit", ""),
                    "row": item.get("row", 0),
                    "additional_control": item.get("additional_control", ""),
                }

                item_data["columnErrors"] = item.get("column_errors", [])
                for error_field in [
                    "entity_error",
                    "section_error",
                    "resource_error",
                    "additional_control_error",
                    "amount_error",
                    "unit_price_error",
                    "general_error",
                ]:
                    if error_field in item:
                        item_data[error_field] = item[error_field]
                preview_data["contract_items_unit_price"].append(item_data)
        return preview_data

    def process_excel(self):
        self.created_contract_items_unit_price = []
        self.preview_contract_items_unit_price = []
        self.errors = []

        self.file_name = self.download_excel_file()
        if not self.file_name:
            return False

        self.load_data()
        if not self.wb:
            return False

        if not self.process_info_sheet():
            return False
        self.process_items_sheet()

        for item in self.preview_contract_items_unit_price:
            if item["column_errors"]:
                return False

        shared_clean_up(self.file_name, self.temp_path)
        return True


def generate_preview(excel_import_id, user_id):
    try:
        excel_import = ExcelImport.objects.get(pk=excel_import_id)
        user = User.objects.get(pk=user_id)

        importer = ImportContractItemUnitPrice(excel_import, user)
        success = importer.process_excel()

        preview_data = importer.get_preview_data()
        json_data = json.dumps(preview_data)

        excel_import.preview_file.save(
            f"{excel_import.uuid}.json", ContentFile(json_data.encode("utf-8"))
        )

        excel_import.generating_preview = False
        excel_import.error = not success
        excel_import.save()
        return excel_import
    except Exception as e:
        logging.error(f"Error in generate_preview: {str(e)}")
        if excel_import:
            excel_import = ExcelImport.objects.get(pk=excel_import_id)
            excel_import.generating_preview = False
            excel_import.error = True
            excel_import.save()
        return None


def execute_import(excel_import_id):
    try:
        excel_import = ExcelImport.objects.get(pk=excel_import_id)
        if excel_import.done:
            return True

        if excel_import.error:
            return False

        importer = ImportContractItemUnitPrice(excel_import, excel_import.created_by)

        if excel_import.preview_file:
            preview_content = excel_import.preview_file.read()
            preview_data = json.loads(preview_content)

            if (
                isinstance(preview_data, dict)
                and "contract_id" in preview_data
                and "contract_items_unit_price" in preview_data
            ):
                success = create_contract_items_from_preview(importer, preview_data)
                excel_import.generating_preview = False
                excel_import.done = True
                excel_import.error = not success
                excel_import.save()

                return success

        excel_import.error = True
        excel_import.save()
        return False
    except Exception as e:
        logging.error(f"Error in execute_import: {str(e)}")
        excel_import.error = True
        excel_import.save()
        return False


def create_contract_items_from_preview(importer, preview_data):
    permissions = PermissionManager(
        user=importer.user,
        company_ids=importer.company,
        model="ContractItemUnitPrice",
    )
    if not permissions.has_permission(permission="can_create"):
        sentry_sdk.capture_exception(
            "kartado.error.contract_item_unit_price.user_does_not_have_permission_to_create"
        )
        return False

    contract_items = []
    contract_id = preview_data.get("contract_id")
    contract = Contract.objects.get(uuid=contract_id)

    for item in preview_data.get("contract_items_unit_price", []):
        if "columnErrors" in item and item["columnErrors"]:
            break

        try:
            if item.get("resource_name"):
                resource = Resource.objects.create(
                    name=item["resource_name"],
                    company=importer.company,
                    unit=item.get("unit", ""),
                )
            else:
                resource = None

            if item.get("entity_name"):
                entity = Entity.objects.filter(
                    company=importer.company,
                    name=item["entity_name"].strip(),
                ).first()
            else:
                entity = None

            if item.get("section_name"):
                section = ContractService.objects.filter(
                    description=item["section_name"].strip(),
                    firms__company=importer.company,
                    unit_price_service_contracts__uuid=contract_id,
                ).first()
            else:
                section = None

            additional_control_obj = None
            if item.get("additional_control"):
                additional_control_obj = AdditionalControl.objects.filter(
                    company=importer.company,
                    name=item.get("additional_control").strip(),
                    is_active=True,
                ).first()

            sor_data = {
                "uuid": uuid.uuid4(),
                "amount": item["amount"],
                "unit_price": item["unit_price"],
                "created_by": importer.user,
                "contract": contract,
                "resource": resource,
            }

            if entity:
                sor_data["entity"] = entity

            if additional_control_obj:
                sor_data["additional_control_model"] = additional_control_obj
                # sor_data["additional_control"] = item.get("additional_control")

            service_order_resource = ServiceOrderResource.objects.create(**sor_data)

            last_order = ContractItemUnitPrice.objects.filter(
                contract_item_unit_price_services=section,
                resource__contract=contract,
            ).aggregate(Max("order"))["order__max"]

            if last_order is None:
                last_order = 0

            contract_item_data = {
                "uuid": uuid.uuid4(),
                "sort_string": item["sort_string"],
                "resource": service_order_resource,
                "order": last_order + 1,
                "was_from_import": True,
            }

            if entity:
                contract_item_data["entity"] = entity

            contract_item = ContractItemUnitPrice.objects.create(**contract_item_data)

            if section:
                contract_item.contract_item_unit_price_services.add(section)

            contract_items.append(contract_item)

            excel_contract_item = {
                "contract_item_unit_price_id": str(contract_item.uuid),
                "excel_import_id": str(importer.excel_import.uuid),
                "row": str(item.get("row", 0)),
                "operation": "CREATE",
            }

            serialized_excel_contract_item = ExcelContractItemUnitPriceSerializer(
                data=excel_contract_item
            )

            if serialized_excel_contract_item.is_valid():
                ExcelContractItemUnitPrice.objects.create(**excel_contract_item)

        except Exception as e:
            logging.error(f"Error creating contract item: {str(e)}")
            continue

    if contract_items:
        calculate_contract_prices(str(contract.uuid))

    return len(contract_items) > 0
