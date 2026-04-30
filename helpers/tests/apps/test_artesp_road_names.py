"""
Testes unitários para o módulo artesp_road_names.

Este módulo contém testes para a função get_artesp_full_road_name que
resolve nomes completos de rodovias em relatórios ARTESP.
"""

from unittest.mock import MagicMock

from helpers.apps.ccr_report_utils.artesp_road_names import get_artesp_full_road_name


class TestGetArtespFullRoadName:
    """Tests for the get_artesp_full_road_name function"""

    def test_get_full_road_name_with_single_interval(self):
        """Test rodovia com um único intervalo, km dentro do intervalo"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 123
        reporting.road_name = "SP-348"
        reporting.km = 25.5

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "123": [
                    {
                        "km_begin": 0.0,
                        "km_end": 50.0,
                        "full_name": "SP-348 - Rodovia dos Bandeirantes",
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-348 - Rodovia dos Bandeirantes"

    def test_get_full_road_name_with_multiple_intervals(self):
        """Test rodovia com múltiplos intervalos, retorna o correto baseado no km"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 456
        reporting.road_name = "SP-330"
        reporting.km = 75.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "456": [
                    {
                        "km_begin": 0.0,
                        "km_end": 50.0,
                        "full_name": "SP-330 - Trecho Sul",
                    },
                    {
                        "km_begin": 50.0,
                        "km_end": 100.0,
                        "full_name": "SP-330 - Trecho Norte",
                    },
                    {
                        "km_begin": 100.0,
                        "km_end": 150.0,
                        "full_name": "SP-330 - Trecho Extremo Norte",
                    },
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-330 - Trecho Norte"

    def test_get_full_road_name_km_at_boundary_begin(self):
        """Test km exatamente no limite do intervalo (início)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 789
        reporting.road_name = "SP-065"
        reporting.km = 50.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "789": [
                    {
                        "km_begin": 50.0,
                        "km_end": 100.0,
                        "full_name": "SP-065 - Rodovia Dom Pedro I",
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-065 - Rodovia Dom Pedro I"

    def test_get_full_road_name_km_at_boundary_end(self):
        """Test km exatamente no limite do intervalo (fim)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 789
        reporting.road_name = "SP-065"
        reporting.km = 100.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "789": [
                    {
                        "km_begin": 50.0,
                        "km_end": 100.0,
                        "full_name": "SP-065 - Rodovia Dom Pedro I",
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-065 - Rodovia Dom Pedro I"

    def test_get_full_road_name_km_outside_intervals(self):
        """Test km fora dos intervalos definidos (fallback)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 999
        reporting.road_name = "SP-280"
        reporting.km = 200.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "999": [
                    {
                        "km_begin": 0.0,
                        "km_end": 100.0,
                        "full_name": "SP-280 - Rodovia Castelo Branco",
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-280"  # Fallback para road_name

    def test_get_full_road_name_no_mapping_key(self):
        """Test Company sem artesp_report_road_names no metadata (fallback)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 111
        reporting.road_name = "SP-160"
        reporting.km = 25.0

        company = MagicMock()
        company.metadata = {"other_config": {"some_key": "some_value"}}

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-160"  # Fallback para road_name

    def test_get_full_road_name_road_not_in_mapping(self):
        """Test Rodovia não está no mapeamento (fallback)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 222
        reporting.road_name = "SP-070"
        reporting.km = 15.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "333": [
                    {
                        "km_begin": 0.0,
                        "km_end": 50.0,
                        "full_name": "SP-333 - Outra Rodovia",
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-070"  # Fallback para road_name

    def test_get_full_road_name_no_road_fk(self):
        """Test Reporting sem road_id (fallback)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = None
        reporting.road_name = "BR-101"
        reporting.km = 50.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "123": [
                    {
                        "km_begin": 0.0,
                        "km_end": 100.0,
                        "full_name": "BR-101 - Rodovia Rio-Santos",
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "BR-101"  # Fallback para road_name

    def test_get_full_road_name_no_km(self):
        """Test Reporting sem km (fallback)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 555
        reporting.road_name = "SP-270"
        reporting.km = None

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "555": [
                    {
                        "km_begin": 0.0,
                        "km_end": 100.0,
                        "full_name": "SP-270 - Rodovia Raposo Tavares",
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-270"  # Fallback para road_name

    def test_get_full_road_name_empty_metadata(self):
        """Test Company com metadata vazio ou None (fallback)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 666
        reporting.road_name = "SP-310"
        reporting.km = 30.0

        # Test com metadata None
        company = MagicMock()
        company.metadata = None

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-310"  # Fallback para road_name

    def test_get_full_road_name_company_none(self):
        """Test Company None (fallback)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 777
        reporting.road_name = "SP-300"
        reporting.km = 40.0

        company = None

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-300"  # Fallback para road_name

    def test_get_full_road_name_road_name_none_fallback(self):
        """Test Reporting com road_name None retorna string vazia como fallback"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = None
        reporting.road_name = None
        reporting.km = 50.0

        company = MagicMock()
        company.metadata = {"artesp_report_road_names": {}}

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == ""  # Fallback para string vazia quando road_name é None

    def test_get_full_road_name_interval_without_km_end(self):
        """Test intervalo sem km_end especificado (usa infinito)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 888
        reporting.road_name = "SP-318"
        reporting.km = 500.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "888": [
                    {
                        "km_begin": 0.0,
                        # km_end não especificado - deve usar float('inf')
                        "full_name": "SP-318 - Rodovia Thales de Lorena Peixoto Jr.",
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-318 - Rodovia Thales de Lorena Peixoto Jr."

    def test_get_full_road_name_interval_without_km_begin(self):
        """Test intervalo sem km_begin especificado (usa 0)"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 999
        reporting.road_name = "SP-191"
        reporting.km = 5.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "999": [
                    {
                        # km_begin não especificado - deve usar 0
                        "km_end": 50.0,
                        "full_name": "SP-191 - Rodovia Wilson Finardi",
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-191 - Rodovia Wilson Finardi"

    def test_get_full_road_name_first_match_wins(self):
        """Test que a primeira correspondência é retornada em múltiplos intervalos"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 1010
        reporting.road_name = "SP-225"
        reporting.km = 100.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "1010": [
                    {
                        "km_begin": 50.0,
                        "km_end": 150.0,
                        "full_name": "SP-225 - Primeiro Intervalo",
                    },
                    {
                        "km_begin": 90.0,
                        "km_end": 120.0,
                        "full_name": "SP-225 - Segundo Intervalo Sobreposto",
                    },
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        # Deve retornar o primeiro intervalo que corresponder
        assert result == "SP-225 - Primeiro Intervalo"

    def test_get_full_road_name_interval_without_full_name(self):
        """Test intervalo sem full_name usa fallback"""
        # Arrange
        reporting = MagicMock()
        reporting.road_id = 1111
        reporting.road_name = "SP-099"
        reporting.km = 25.0

        company = MagicMock()
        company.metadata = {
            "artesp_report_road_names": {
                "1111": [
                    {
                        "km_begin": 0.0,
                        "km_end": 50.0,
                        # full_name não especificado
                    }
                ]
            }
        }

        # Act
        result = get_artesp_full_road_name(reporting, company)

        # Assert
        assert result == "SP-099"  # Fallback quando full_name não existe
