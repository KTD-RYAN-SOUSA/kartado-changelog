from django.test import TestCase

from helpers.language import MONTH_ABBREVIATIONS_PT_BR, MONTH_PT_BR


class TestLanguageConstants(TestCase):
    """Tests for language constants"""

    def test_month_pt_br_has_all_months(self):
        """Test that MONTH_PT_BR contains all 12 months"""
        assert len(MONTH_PT_BR) == 12

    def test_month_pt_br_january(self):
        """Test January translation"""
        assert MONTH_PT_BR["January"] == "Janeiro"

    def test_month_pt_br_february(self):
        """Test February translation"""
        assert MONTH_PT_BR["February"] == "Fevereiro"

    def test_month_pt_br_march(self):
        """Test March translation"""
        assert MONTH_PT_BR["March"] == "Março"

    def test_month_pt_br_april(self):
        """Test April translation"""
        assert MONTH_PT_BR["April"] == "Abril"

    def test_month_pt_br_may(self):
        """Test May translation"""
        assert MONTH_PT_BR["May"] == "Maio"

    def test_month_pt_br_june(self):
        """Test June translation"""
        assert MONTH_PT_BR["June"] == "Junho"

    def test_month_pt_br_july(self):
        """Test July translation"""
        assert MONTH_PT_BR["July"] == "Julho"

    def test_month_pt_br_august(self):
        """Test August translation"""
        assert MONTH_PT_BR["August"] == "Agosto"

    def test_month_pt_br_september(self):
        """Test September translation"""
        assert MONTH_PT_BR["September"] == "Setembro"

    def test_month_pt_br_october(self):
        """Test October translation"""
        assert MONTH_PT_BR["October"] == "Outubro"

    def test_month_pt_br_november(self):
        """Test November translation"""
        assert MONTH_PT_BR["November"] == "Novembro"

    def test_month_pt_br_december(self):
        """Test December translation"""
        assert MONTH_PT_BR["December"] == "Dezembro"

    def test_month_abbreviations_pt_br_has_all_months(self):
        """Test that MONTH_ABBREVIATIONS_PT_BR contains all 12 months"""
        assert len(MONTH_ABBREVIATIONS_PT_BR) == 12

    def test_month_abbreviations_pt_br_jan(self):
        """Test Jan abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Jan"] == "Jan"

    def test_month_abbreviations_pt_br_feb(self):
        """Test Feb abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Feb"] == "Fev"

    def test_month_abbreviations_pt_br_mar(self):
        """Test Mar abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Mar"] == "Mar"

    def test_month_abbreviations_pt_br_apr(self):
        """Test Apr abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Apr"] == "Abr"

    def test_month_abbreviations_pt_br_may(self):
        """Test May abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["May"] == "Mai"

    def test_month_abbreviations_pt_br_jun(self):
        """Test Jun abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Jun"] == "Jun"

    def test_month_abbreviations_pt_br_jul(self):
        """Test Jul abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Jul"] == "Jul"

    def test_month_abbreviations_pt_br_aug(self):
        """Test Aug abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Aug"] == "Ago"

    def test_month_abbreviations_pt_br_sep(self):
        """Test Sep abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Sep"] == "Set"

    def test_month_abbreviations_pt_br_oct(self):
        """Test Oct abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Oct"] == "Out"

    def test_month_abbreviations_pt_br_nov(self):
        """Test Nov abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Nov"] == "Nov"

    def test_month_abbreviations_pt_br_dec(self):
        """Test Dec abbreviation"""
        assert MONTH_ABBREVIATIONS_PT_BR["Dec"] == "Dez"
