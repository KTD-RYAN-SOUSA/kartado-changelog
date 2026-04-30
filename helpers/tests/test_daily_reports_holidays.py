from datetime import date
from unittest.mock import MagicMock

from helpers.apps.daily_reports import is_holiday_for_firm


def build_holidays_custom_options(holidays_list):
    """Helper para construir a estrutura de custom_options com holidays"""
    return {"dailyReportHolidays": {"fields": {"holidays": holidays_list}}}


class TestIsHolidayForFirm:
    """Testes para funcao is_holiday_for_firm"""

    def test_national_holiday_returns_true(self):
        """Feriado nacional deve retornar True"""
        company = MagicMock()
        company.custom_options = {}
        # 2025-01-01 esta em HOLIDAYS
        result = is_holiday_for_firm(company, "any-firm-id", date(2025, 1, 1))
        assert result is True

    def test_non_holiday_returns_false(self):
        """Dia normal deve retornar False"""
        company = MagicMock()
        company.custom_options = {}
        result = is_holiday_for_firm(company, "any-firm-id", date(2025, 6, 15))
        assert result is False

    def test_custom_holiday_empty_firms_returns_false(self):
        """Feriado customizado com firms vazio nao aplica a nenhuma equipe"""
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [{"date": "2025-06-24", "name": "Sao Joao", "firms": [], "repeat": False}]
        )
        result = is_holiday_for_firm(company, "any-firm-id", date(2025, 6, 24))
        assert result is False

    def test_custom_holiday_specific_firm_matches(self):
        """Feriado customizado para equipe especifica - equipe correta"""
        firm_id = "firm-uuid-123"
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [{"date": "2025-06-24", "firms": [firm_id], "repeat": False}]
        )
        result = is_holiday_for_firm(company, firm_id, date(2025, 6, 24))
        assert result is True

    def test_custom_holiday_specific_firm_not_matches(self):
        """Feriado customizado para equipe especifica - equipe diferente"""
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [{"date": "2025-06-24", "firms": ["other-firm"], "repeat": False}]
        )
        result = is_holiday_for_firm(company, "my-firm", date(2025, 6, 24))
        assert result is False

    def test_repeat_annually_same_day_future_year(self):
        """Feriado com repeat=True deve funcionar em anos futuros"""
        firm_id = "firm-uuid-123"
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [{"date": "2025-06-24", "firms": [firm_id], "repeat": True}]
        )
        # Mesmo dia/mes, ano futuro
        result = is_holiday_for_firm(company, firm_id, date(2030, 6, 24))
        assert result is True

    def test_repeat_annually_same_day_past_year(self):
        """Feriado com repeat=True NAO deve funcionar em anos anteriores"""
        firm_id = "firm-uuid-123"
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [{"date": "2026-02-16", "firms": [firm_id], "repeat": True}]
        )
        # Mesmo dia/mes, mas ano anterior ao feriado
        result = is_holiday_for_firm(company, firm_id, date(2025, 2, 16))
        assert result is False

    def test_repeat_false_different_year(self):
        """Feriado com repeat=False NAO deve funcionar em anos diferentes"""
        firm_id = "firm-uuid-123"
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [{"date": "2025-06-24", "firms": [firm_id], "repeat": False}]
        )
        result = is_holiday_for_firm(company, firm_id, date(2026, 6, 24))
        assert result is False

    def test_none_date_returns_false(self):
        """Data None deve retornar False"""
        company = MagicMock()
        result = is_holiday_for_firm(company, "any-firm", None)
        assert result is False

    def test_none_company_checks_only_national(self):
        """Company None deve verificar apenas nacionais"""
        # Feriado nacional
        result = is_holiday_for_firm(None, "any-firm", date(2025, 1, 1))
        assert result is True
        # Dia normal
        result = is_holiday_for_firm(None, "any-firm", date(2025, 6, 15))
        assert result is False

    def test_multiple_holidays_on_same_date_different_firms(self):
        """Multiplos feriados na mesma data para equipes diferentes"""
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [
                {"date": "2025-06-24", "firms": ["firm-a"], "repeat": False},
                {"date": "2025-06-24", "firms": ["firm-b"], "repeat": False},
            ]
        )
        # Firm A deve ter feriado
        assert is_holiday_for_firm(company, "firm-a", date(2025, 6, 24)) is True
        # Firm B deve ter feriado
        assert is_holiday_for_firm(company, "firm-b", date(2025, 6, 24)) is True
        # Firm C nao deve ter feriado
        assert is_holiday_for_firm(company, "firm-c", date(2025, 6, 24)) is False

    def test_invalid_date_format_is_skipped(self):
        """Data em formato invalido no custom_options deve ser ignorada"""
        firm_id = "firm-uuid-123"
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [
                {"date": "invalid-date", "firms": [firm_id], "repeat": False},
                {"date": "2025-06-24", "firms": [firm_id], "repeat": False},
            ]
        )
        # Deve funcionar pois a data invalida e ignorada
        result = is_holiday_for_firm(company, firm_id, date(2025, 6, 24))
        assert result is True

    def test_missing_date_field_is_skipped(self):
        """Feriado sem campo date deve ser ignorado"""
        firm_id = "firm-uuid-123"
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [
                {"name": "Feriado sem data", "firms": [firm_id], "repeat": False},
                {"date": "2025-06-24", "firms": [firm_id], "repeat": False},
            ]
        )
        # Deve funcionar pois o feriado sem data e ignorado
        result = is_holiday_for_firm(company, firm_id, date(2025, 6, 24))
        assert result is True

    def test_none_firm_id_with_custom_holiday(self):
        """firm_id None nao deve corresponder a feriados customizados"""
        company = MagicMock()
        company.custom_options = build_holidays_custom_options(
            [{"date": "2025-06-24", "firms": ["any-firm"], "repeat": False}]
        )
        result = is_holiday_for_firm(company, None, date(2025, 6, 24))
        assert result is False

    def test_custom_options_none(self):
        """Company com custom_options None deve verificar apenas nacionais"""
        company = MagicMock()
        company.custom_options = None
        # Feriado nacional
        result = is_holiday_for_firm(company, "any-firm", date(2025, 1, 1))
        assert result is True
        # Dia normal
        result = is_holiday_for_firm(company, "any-firm", date(2025, 6, 15))
        assert result is False

    def test_empty_dailyReportHolidays_object(self):
        """dailyReportHolidays como objeto vazio deve retornar False"""
        company = MagicMock()
        company.custom_options = {"dailyReportHolidays": {}}
        result = is_holiday_for_firm(company, "any-firm", date(2025, 6, 24))
        assert result is False

    def test_missing_fields_key(self):
        """dailyReportHolidays sem key 'fields' deve retornar False"""
        company = MagicMock()
        company.custom_options = {"dailyReportHolidays": {"other": "value"}}
        result = is_holiday_for_firm(company, "any-firm", date(2025, 6, 24))
        assert result is False

    def test_missing_holidays_key(self):
        """dailyReportHolidays.fields sem key 'holidays' deve retornar False"""
        company = MagicMock()
        company.custom_options = {"dailyReportHolidays": {"fields": {}}}
        result = is_holiday_for_firm(company, "any-firm", date(2025, 6, 24))
        assert result is False
