"""
Testes do validator de CNPJ alfanumérico (IN RFB nº 2.229/2024).

Cobre:
- Compatibilidade total com CNPJs numéricos legados (formatado e sem máscara)
- Aceitação do novo formato alfanumérico
- Conversão automática de minúsculas para maiúsculas
- Mensagens i18n específicas para cada tipo de erro
- Geradora `generate_cnpj()` produzindo CNPJs válidos nos dois formatos
"""

import pytest
from django.forms import ValidationError

from helpers.validators.brazilian_documents import (
    CNPJ_DV1_WEIGHTS,
    CNPJ_DV2_WEIGHTS,
    _cnpj_calc_dv,
    generate_cnpj,
    validate_CNPJ,
)


class TestValidateCNPJLegacyNumeric:
    """Garante que CNPJs numéricos antigos seguem aceitos sem mudança."""

    def test_accepts_formatted_numeric(self):
        assert validate_CNPJ("09.481.248/0001-96") == "09.481.248/0001-96"

    def test_accepts_unformatted_numeric(self):
        assert validate_CNPJ("09481248000196") == "09481248000196"

    def test_accepts_other_formatted_numeric(self):
        assert validate_CNPJ("95.633.459/0001-39") == "95.633.459/0001-39"

    def test_accepts_unformatted_subcompany_fixture_value(self):
        assert validate_CNPJ("91742417000185") == "91742417000185"

    def test_accepts_firm_fixture_value(self):
        assert validate_CNPJ("29.128.809/0001-85") == "29.128.809/0001-85"


class TestValidateCNPJAlphanumeric:
    """Cobertura do novo formato alfanumérico (IN RFB 2.229/2024)."""

    def test_accepts_serpro_example_formatted(self):
        # Exemplo oficial do Serpro: 12.ABC.345/01DE-35
        assert validate_CNPJ("12.ABC.345/01DE-35") == "12.ABC.345/01DE-35"

    def test_accepts_serpro_example_unformatted(self):
        assert validate_CNPJ("12ABC34501DE35") == "12ABC34501DE35"

    def test_converts_lowercase_to_uppercase(self):
        # RN05: minúsculas viram maiúsculas automaticamente
        assert validate_CNPJ("12.abc.345/01de-35") == "12.ABC.345/01DE-35"
        assert validate_CNPJ("12abc34501de35") == "12ABC34501DE35"

    def test_accepts_mixed_case(self):
        assert validate_CNPJ("12.AbC.345/01dE-35") == "12.ABC.345/01DE-35"


class TestValidateCNPJRejections:
    """Mensagens de erro i18n específicas para cada tipo de problema."""

    def test_rejects_too_short_with_max_digits_message(self):
        with pytest.raises(ValidationError) as exc:
            validate_CNPJ("12.ABC.345/01DE-3")
        assert "kartado.error.cnpj_max_digits" in str(exc.value)

    def test_rejects_too_long_with_max_digits_message(self):
        with pytest.raises(ValidationError) as exc:
            validate_CNPJ("12.ABC.345/01DE-355")
        assert "kartado.error.cnpj_max_digits" in str(exc.value)

    def test_rejects_letter_in_dv_position_with_specific_message(self):
        # RN03: letra nas 2 últimas posições recebe mensagem própria
        with pytest.raises(ValidationError) as exc:
            validate_CNPJ("12ABC34501DE3X")
        assert "kartado.error.cnpj_dv_must_be_digits" in str(exc.value)

    def test_rejects_special_character_with_invalid_characters_message(self):
        with pytest.raises(ValidationError) as exc:
            validate_CNPJ("12@BC34501DE35")
        assert "kartado.error.cnpj_invalid_characters" in str(exc.value)

    def test_rejects_wrong_dv_with_invalid_message(self):
        with pytest.raises(ValidationError) as exc:
            validate_CNPJ("12ABC34501DE34")
        assert "kartado.error.cnpj_invalid" in str(exc.value)

    def test_accepts_zeroed_cnpj(self):
        # CNPJ zerado tem DV válido matematicamente e pode existir em dados legados;
        # o billing já o exclui via .exclude(cnpj__contains="00000000000000").
        assert validate_CNPJ("00000000000000") == "00000000000000"

    def test_rejects_wrong_dv_in_legacy_numeric(self):
        # Garante que numérico inválido segue rejeitado
        with pytest.raises(ValidationError) as exc:
            validate_CNPJ("09.481.248/0001-99")
        assert "kartado.error.cnpj_invalid" in str(exc.value)


class TestValidateCNPJEmpty:
    """Valores vazios não disparam erro — preservam o comportamento legado."""

    def test_empty_string_returns_empty(self):
        assert validate_CNPJ("") == ""

    def test_none_returns_empty(self):
        assert validate_CNPJ(None) == ""


class TestGenerateCnpj:
    """A geradora deve produzir CNPJs válidos para os dois formatos."""

    def test_generate_numeric_default(self):
        for _ in range(20):
            cnpj = generate_cnpj()
            # Deve ser aceito pelo validator
            assert validate_CNPJ(cnpj) == cnpj
            # Não pode conter letras (formato legado)
            cleaned = cnpj.replace(".", "").replace("/", "").replace("-", "")
            assert cleaned.isdigit()

    def test_generate_numeric_explicit(self):
        for _ in range(20):
            cnpj = generate_cnpj(alphanumeric=False)
            assert validate_CNPJ(cnpj) == cnpj
            cleaned = cnpj.replace(".", "").replace("/", "").replace("-", "")
            assert cleaned.isdigit()

    def test_generate_alphanumeric(self):
        for _ in range(20):
            cnpj = generate_cnpj(alphanumeric=True)
            # Deve ser aceito pelo validator
            assert validate_CNPJ(cnpj) == cnpj
            cleaned = cnpj.replace(".", "").replace("/", "").replace("-", "")
            # DV (2 últimas) sempre numéricas
            assert cleaned[-2:].isdigit()
            # Tamanho correto
            assert len(cleaned) == 14

    def test_generate_alphanumeric_eventually_produces_letters(self):
        # Sanity check: ao gerar muitos, ao menos um deve ter letra
        # (probabilidade de NÃO ter letra em 12 sorteios entre 36 chars
        #  é (10/36)^12 ≈ 4.7e-7 — basicamente zero)
        any_letter = False
        for _ in range(50):
            cnpj = generate_cnpj(alphanumeric=True)
            cleaned = cnpj.replace(".", "").replace("/", "").replace("-", "")
            if any(c.isalpha() for c in cleaned):
                any_letter = True
                break
        assert any_letter


class TestCNPJDVCalculation:
    """Testes de baixo nível do cálculo do DV — protege contra regressões
    silenciosas se alguém alterar pesos ou a função `_cnpj_char_value`."""

    def test_serpro_example_dv1(self):
        # 12.ABC.345/01DE-35 → DV1 esperado = 3
        assert _cnpj_calc_dv("12ABC34501DE", CNPJ_DV1_WEIGHTS) == 3

    def test_serpro_example_dv2(self):
        # base + DV1 = "12ABC34501DE3" → DV2 esperado = 5
        assert _cnpj_calc_dv("12ABC34501DE3", CNPJ_DV2_WEIGHTS) == 5

    def test_legacy_numeric_dv1(self):
        # 09481248000196 → DV1 esperado = 9
        assert _cnpj_calc_dv("094812480001", CNPJ_DV1_WEIGHTS) == 9

    def test_legacy_numeric_dv2(self):
        # base + DV1 = "0948124800019" → DV2 esperado = 6
        assert _cnpj_calc_dv("0948124800019", CNPJ_DV2_WEIGHTS) == 6
