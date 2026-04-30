from unittest.mock import Mock

import pytest
from django.test import TestCase

from helpers.apps.antt_attachment_excel_report import AnttAttachmentExcelReport


class TestNormalizeIdOccurrenceType(TestCase):
    """Tests for _normalize_id_occurrence_type static method"""

    def test_string_returns_list_with_single_element(self):
        result = AnttAttachmentExcelReport._normalize_id_occurrence_type(
            "3f02d0d3-1a01-4ccf-8145-dd13554cacb6"
        )
        assert result == ["3f02d0d3-1a01-4ccf-8145-dd13554cacb6"]

    def test_list_returns_same_list(self):
        uuids = [
            "3f02d0d3-1a01-4ccf-8145-dd13554cacb6",
            "a797c36c-8dda-4cb1-bcf8-14b900c05730",
        ]
        result = AnttAttachmentExcelReport._normalize_id_occurrence_type(uuids)
        assert result == uuids

    def test_none_returns_empty_list(self):
        result = AnttAttachmentExcelReport._normalize_id_occurrence_type(None)
        assert result == []

    def test_empty_list_returns_empty_list(self):
        result = AnttAttachmentExcelReport._normalize_id_occurrence_type([])
        assert result == []

    def test_empty_string_returns_list_with_empty_string(self):
        result = AnttAttachmentExcelReport._normalize_id_occurrence_type("")
        assert result == [""]


class TestIsClassBasedType(TestCase):
    """Tests for _is_class_based_type static method"""

    def test_with_api_name_returns_false(self):
        """Modo campo: campo 'type' tem apiName"""
        occ_snake = {
            "form_fields": [
                {
                    "name": "type",
                    "apiName": "amountType",
                    "options": [{"name": "Descida", "value": "1"}],
                }
            ]
        }
        assert AnttAttachmentExcelReport._is_class_based_type(occ_snake) is False

    def test_without_api_name_returns_true(self):
        """Modo classe: campo 'type' sem apiName"""
        occ_snake = {
            "form_fields": [
                {
                    "name": "type",
                    "options": [
                        {
                            "name": "Descida",
                            "value": ["3f02d0d3-1a01-4ccf-8145-dd13554cacb6"],
                        }
                    ],
                }
            ]
        }
        assert AnttAttachmentExcelReport._is_class_based_type(occ_snake) is True

    def test_no_type_field_returns_false(self):
        """Sem campo 'type' nos formFields"""
        occ_snake = {
            "form_fields": [{"name": "flow", "apiName": "flowDirection", "options": []}]
        }
        assert AnttAttachmentExcelReport._is_class_based_type(occ_snake) is False

    def test_empty_form_fields_returns_false(self):
        occ_snake = {"form_fields": []}
        assert AnttAttachmentExcelReport._is_class_based_type(occ_snake) is False

    def test_none_form_fields_returns_false(self):
        occ_snake = {"form_fields": None}
        assert AnttAttachmentExcelReport._is_class_based_type(occ_snake) is False

    def test_missing_form_fields_returns_false(self):
        occ_snake = {}
        assert AnttAttachmentExcelReport._is_class_based_type(occ_snake) is False

    def test_with_camel_case_keys(self):
        """Garante que to_snake_case e aplicado nas chaves do field"""
        occ_snake = {
            "form_fields": [
                {
                    "name": "type",
                    "apiName": "amountType",
                    "options": [],
                }
            ]
        }
        assert AnttAttachmentExcelReport._is_class_based_type(occ_snake) is False

    def test_type_field_with_empty_api_name_returns_true(self):
        """apiName presente mas vazio e tratado como ausente"""
        occ_snake = {
            "form_fields": [
                {
                    "name": "type",
                    "apiName": "",
                    "options": [],
                }
            ]
        }
        assert AnttAttachmentExcelReport._is_class_based_type(occ_snake) is True


class TestValidateOccurrenceTypeUuids(TestCase):
    """Tests for _validate_occurrence_type_uuids with list support"""

    def _make_report(self, allowed_list, occurrence_type_uuids):
        """Cria instancia sem chamar __init__, setando atributos manualmente."""
        report = object.__new__(AnttAttachmentExcelReport)
        report.allowed_occurrence_types_antt_attachment = allowed_list
        report.occurrence_type_uuids = occurrence_type_uuids
        return report

    def test_string_id_occurrence_type_retrocompat(self):
        """Retrocompatibilidade: idOccurrenceType como string"""
        report = self._make_report(
            allowed_list=[
                {"id_occurrence_type": "uuid-1", "form_fields": []},
            ],
            occurrence_type_uuids=["uuid-1"],
        )
        result = report._validate_occurrence_type_uuids()
        assert result is True
        assert "uuid-1" in report.occurrence_type_uuids

    def test_list_id_occurrence_type(self):
        """Novo: idOccurrenceType como lista"""
        report = self._make_report(
            allowed_list=[
                {
                    "id_occurrence_type": ["uuid-1", "uuid-2"],
                    "form_fields": [],
                },
            ],
            occurrence_type_uuids=["uuid-1"],
        )
        result = report._validate_occurrence_type_uuids()
        assert result is True

    def test_list_id_occurrence_type_accepts_all_uuids(self):
        """Todos os UUIDs de uma lista sao aceitos como validos"""
        report = self._make_report(
            allowed_list=[
                {
                    "id_occurrence_type": ["uuid-1", "uuid-2", "uuid-3"],
                    "form_fields": [],
                },
            ],
            occurrence_type_uuids=["uuid-2"],
        )
        result = report._validate_occurrence_type_uuids()
        assert result is True

    def test_mixed_string_and_list_entries(self):
        """Entradas mistas: uma com string, outra com lista"""
        report = self._make_report(
            allowed_list=[
                {"id_occurrence_type": "uuid-1", "form_fields": []},
                {
                    "id_occurrence_type": ["uuid-2", "uuid-3"],
                    "form_fields": [],
                },
            ],
            occurrence_type_uuids=["uuid-3"],
        )
        result = report._validate_occurrence_type_uuids()
        assert result is True

    def test_invalid_uuid_raises_error(self):
        """UUID invalido continua sendo rejeitado"""
        report = self._make_report(
            allowed_list=[
                {
                    "id_occurrence_type": ["uuid-1", "uuid-2"],
                    "form_fields": [],
                },
            ],
            occurrence_type_uuids=["uuid-invalid"],
        )
        with pytest.raises(ValueError, match="IDs de occurrence_type não permitidos"):
            report._validate_occurrence_type_uuids()

    def test_no_occurrence_type_uuids_skips_validation(self):
        """Sem occurrence_type_uuids, validacao e pulada"""
        report = self._make_report(
            allowed_list=[
                {"id_occurrence_type": "uuid-1", "form_fields": []},
            ],
            occurrence_type_uuids=None,
        )
        result = report._validate_occurrence_type_uuids()
        assert result is None


class TestResolveAmountTypeLabel(TestCase):
    """Tests for _resolve_amount_type_label with dual classification support"""

    UUID_1 = "3f02d0d3-1a01-4ccf-8145-dd13554cacb6"
    UUID_2 = "a797c36c-8dda-4cb1-bcf8-14b900c05730"
    UUID_3 = "f75bd43d-a88a-41f1-ba34-6858b92761e8"

    def _make_report_instance(self, allowed_list):
        """Cria instancia sem __init__ com allowed_list configurada."""
        report = object.__new__(AnttAttachmentExcelReport)
        report.allowed_occurrence_types_antt_attachment = allowed_list
        return report

    def _make_reporting(self, occurrence_type_uuid, form_data=None):
        """Cria mock de Reporting."""
        reporting = Mock()
        reporting.form_data = form_data or {}
        reporting.occurrence_type = Mock()
        reporting.occurrence_type.uuid = occurrence_type_uuid
        return reporting

    # --- Retrocompatibilidade: modo campo com string ---

    def test_field_mode_string_type_label(self):
        """Modo campo com idOccurrenceType string retorna label correto"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": self.UUID_1,
                    "formFields": [
                        {
                            "name": "type",
                            "apiName": "amountType",
                            "options": [
                                {"name": "Descida", "value": "1"},
                                {"name": "Dissipador", "value": "2"},
                            ],
                        }
                    ],
                }
            ]
        )
        reporting = self._make_reporting(self.UUID_1, form_data={"amountType": "1"})
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "Descida"

    def test_field_mode_string_second_option(self):
        """Modo campo com string, segunda opcao"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": self.UUID_1,
                    "formFields": [
                        {
                            "name": "type",
                            "apiName": "amountType",
                            "options": [
                                {"name": "Descida", "value": "1"},
                                {"name": "Dissipador", "value": "2"},
                            ],
                        }
                    ],
                }
            ]
        )
        reporting = self._make_reporting(self.UUID_1, form_data={"amountType": "2"})
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "Dissipador"

    def test_field_mode_string_identification(self):
        """Modo campo com string, type_name='identification'"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": self.UUID_1,
                    "formFields": [
                        {
                            "name": "identification",
                            "apiName": "identCode",
                            "options": [],
                        }
                    ],
                }
            ]
        )
        reporting = self._make_reporting(
            self.UUID_1, form_data={"identCode": "ABC-123"}
        )
        result = report._resolve_amount_type_label(reporting, "identification")
        assert result == "ABC-123"

    # --- Modo campo com lista ---

    def test_field_mode_list_type_label(self):
        """Modo campo com idOccurrenceType lista retorna label correto"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": [self.UUID_1, self.UUID_2],
                    "formFields": [
                        {
                            "name": "type",
                            "apiName": "amountType",
                            "options": [
                                {"name": "Descida", "value": "1"},
                                {"name": "Dissipador", "value": "2"},
                            ],
                        }
                    ],
                }
            ]
        )
        reporting = self._make_reporting(self.UUID_2, form_data={"amountType": "1"})
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "Descida"

    def test_field_mode_list_uuid_not_in_list_returns_unavailable(self):
        """UUID do reporting nao esta na lista -> UNAVAILABLE"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": [self.UUID_1],
                    "formFields": [
                        {
                            "name": "type",
                            "apiName": "amountType",
                            "options": [
                                {"name": "Descida", "value": "1"},
                            ],
                        }
                    ],
                }
            ]
        )
        reporting = self._make_reporting(self.UUID_3, form_data={"amountType": "1"})
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "N/A"

    # --- Modo classe (novo) ---

    def test_class_mode_matches_uuid_in_value_array(self):
        """Modo classe: UUID do reporting encontrado no array value"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": [self.UUID_1, self.UUID_2, self.UUID_3],
                    "formFields": [
                        {
                            "name": "type",
                            "options": [
                                {
                                    "name": "Descida",
                                    "value": [self.UUID_1, self.UUID_2],
                                },
                                {
                                    "name": "Dissipador",
                                    "value": [self.UUID_3],
                                },
                            ],
                        }
                    ],
                }
            ]
        )
        reporting = self._make_reporting(self.UUID_1)
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "Descida"

    def test_class_mode_second_option(self):
        """Modo classe: UUID do reporting na segunda opcao"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": [self.UUID_1, self.UUID_2, self.UUID_3],
                    "formFields": [
                        {
                            "name": "type",
                            "options": [
                                {
                                    "name": "Descida",
                                    "value": [self.UUID_1, self.UUID_2],
                                },
                                {
                                    "name": "Dissipador",
                                    "value": [self.UUID_3],
                                },
                            ],
                        }
                    ],
                }
            ]
        )
        reporting = self._make_reporting(self.UUID_3)
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "Dissipador"

    def test_class_mode_uuid_not_found_returns_unavailable(self):
        """Modo classe: UUID nao encontrado em nenhuma option"""
        unknown_uuid = "00000000-0000-0000-0000-000000000000"
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": [self.UUID_1, unknown_uuid],
                    "formFields": [
                        {
                            "name": "type",
                            "options": [
                                {
                                    "name": "Descida",
                                    "value": [self.UUID_1],
                                },
                            ],
                        }
                    ],
                }
            ]
        )
        reporting = self._make_reporting(unknown_uuid)
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "N/A"

    # --- Modo classe: outros type_names continuam com apiName ---

    def test_class_mode_flow_still_uses_api_name(self):
        """No modo classe, 'flow' continua usando apiName normalmente"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": [self.UUID_1],
                    "formFields": [
                        {
                            "name": "type",
                            "options": [
                                {"name": "Dissipador", "value": [self.UUID_1]},
                            ],
                        },
                        {
                            "name": "flow",
                            "apiName": "flowDirection",
                            "options": [
                                {"name": "Montante", "value": "M"},
                                {"name": "Jusante", "value": "J"},
                            ],
                        },
                    ],
                }
            ]
        )
        reporting = self._make_reporting(self.UUID_1, form_data={"flowDirection": "M"})
        result = report._resolve_amount_type_label(reporting, "flow")
        assert result == "Montante"

    # --- Coexistencia ---

    def test_coexistence_field_and_class_modes(self):
        """Entradas com modos diferentes coexistindo na mesma lista"""
        report = self._make_report_instance(
            [
                # Entrada 1: modo campo
                {
                    "idOccurrenceType": self.UUID_1,
                    "formFields": [
                        {
                            "name": "type",
                            "apiName": "amountType",
                            "options": [
                                {"name": "Descida", "value": "1"},
                            ],
                        }
                    ],
                },
                # Entrada 2: modo classe
                {
                    "idOccurrenceType": [self.UUID_2, self.UUID_3],
                    "formFields": [
                        {
                            "name": "type",
                            "options": [
                                {
                                    "name": "Dissipador",
                                    "value": [self.UUID_2, self.UUID_3],
                                },
                            ],
                        }
                    ],
                },
            ]
        )

        # Reporting modo campo
        reporting_field = self._make_reporting(
            self.UUID_1, form_data={"amountType": "1"}
        )
        assert report._resolve_amount_type_label(reporting_field, "type") == "Descida"

        # Reporting modo classe
        reporting_class = self._make_reporting(self.UUID_3)
        assert (
            report._resolve_amount_type_label(reporting_class, "type") == "Dissipador"
        )

    # --- Edge cases ---

    def test_no_reporting_occurrence_type_returns_unavailable(self):
        """Reporting com occurrence_type=None -> str(None)='None' nao faz match"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": self.UUID_1,
                    "formFields": [
                        {
                            "name": "type",
                            "apiName": "amountType",
                            "options": [{"name": "Descida", "value": "1"}],
                        }
                    ],
                }
            ]
        )
        reporting = Mock()
        reporting.form_data = {"amountType": "1"}
        reporting.occurrence_type = None
        # occurrence_type=None -> str(None)="None" -> nao faz match com nenhum UUID
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "N/A"

    def test_reporting_without_occurrence_type_attr_tries_all(self):
        """Reporting sem atributo occurrence_type -> nao filtra, tenta todos"""
        report = self._make_report_instance(
            [
                {
                    "idOccurrenceType": self.UUID_1,
                    "formFields": [
                        {
                            "name": "type",
                            "apiName": "amountType",
                            "options": [{"name": "Descida", "value": "1"}],
                        }
                    ],
                }
            ]
        )
        reporting = Mock(spec=[])
        reporting.form_data = {"amountType": "1"}
        # Sem atributo occurrence_type -> occurrence_type_uuid=None -> nao filtra
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "Descida"

    def test_empty_allowed_list(self):
        """Lista de parametrizacao vazia"""
        report = self._make_report_instance([])
        reporting = self._make_reporting(self.UUID_1)
        result = report._resolve_amount_type_label(reporting, "type")
        assert result == "N/A"
