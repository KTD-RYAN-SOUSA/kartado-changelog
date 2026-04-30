import random
import re
import string

from django.core.validators import EMPTY_VALUES
from django.forms import ValidationError

# CNPJ Alfanumérico (IN RFB nº 2.229/2024)
# A partir de julho/2026 a Receita Federal passa a emitir CNPJs com letras
# nas 12 primeiras posições. As 2 últimas (dígito verificador) continuam
# numéricas. O cálculo do DV segue o Módulo 11 com a conversão
# `valor(c) = ord(c) - 48`, que mantém compatibilidade total com CNPJs
# numéricos legados (dígitos 0-9 → 0-9; letras A-Z → 17-42).
CNPJ_DV1_WEIGHTS = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
CNPJ_DV2_WEIGHTS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
CNPJ_CLEAN_RE = re.compile(r"[./\-]")
CNPJ_FORMAT_RE = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")


def DV_maker(v):
    if v >= 2:
        return 11 - v
    return 0


def _cnpj_char_value(c):
    """Converte um caractere do CNPJ em valor numérico para o cálculo do DV.

    Conforme IN RFB nº 2.229/2024:
    - Dígitos '0'..'9' (ord 48..57) → 0..9
    - Letras 'A'..'Z' (ord 65..90) → 17..42
    """
    return ord(c) - 48


def _cnpj_calc_dv(base, weights):
    total = sum(_cnpj_char_value(ch) * w for ch, w in zip(base, weights))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def validate_CPF(value):
    """
    Value can be either a string in the format XXX.XXX.XXX-XX or an
    11-digit number.
    """
    if not isinstance(value, str):
        value = str(value)
    if value in EMPTY_VALUES:
        return ""
    if not value.isdigit():
        value = re.sub("[-\.]", "", value)  # noqa
    orig_value = value[:]
    try:
        int(value)
    except ValueError:
        raise ValidationError("kartado.error.cpf_digits_only")
    if len(value) != 11:
        raise ValidationError("kartado.error.cpf_max_digits")
    orig_dv = value[-2:]

    new_1dv = sum([i * int(value[idx]) for idx, i in enumerate(range(10, 1, -1))])
    new_1dv = DV_maker(new_1dv % 11)
    value = value[:-2] + str(new_1dv) + value[-1]
    new_2dv = sum([i * int(value[idx]) for idx, i in enumerate(range(11, 1, -1))])
    new_2dv = DV_maker(new_2dv % 11)
    value = value[:-1] + str(new_2dv)
    if value[-2:] != orig_dv:
        raise ValidationError("kartado.error.cpf_invalid")

    return orig_value


def validate_CNPJ(value):
    """
    Aceita CNPJ no formato numérico legado ou alfanumérico
    (IN RFB nº 2.229/2024 — vigente a partir de julho/2026).

    - O valor de entrada pode vir com ou sem máscara `XX.XXX.XXX/XXXX-DD`.
    - Letras minúsculas são convertidas para maiúsculas antes da validação.
    - As 12 primeiras posições aceitam `[0-9A-Z]`; as 2 últimas (dígito
      verificador) aceitam apenas `[0-9]`.
    - O cálculo do DV usa Módulo 11 com pesos canônicos e conversão
      `valor(c) = ord(c) - 48`. CNPJs numéricos antigos seguem válidos com
      o mesmo resultado de antes.
    - Retorna o valor original (com ou sem máscara) em maiúsculo, para
      preservar o formato escolhido pelo usuário durante a persistência.
    """
    if value in EMPTY_VALUES:
        return ""

    value = str(value).upper()
    cleaned = CNPJ_CLEAN_RE.sub("", value)

    if len(cleaned) != 14:
        raise ValidationError("kartado.error.cnpj_max_digits")

    if not CNPJ_FORMAT_RE.match(cleaned):
        # Diferenciamos a mensagem quando o problema é DV não-numérico
        # para dar uma orientação mais precisa ao usuário (RN03).
        if not cleaned[-2:].isdigit():
            raise ValidationError("kartado.error.cnpj_dv_must_be_digits")
        raise ValidationError("kartado.error.cnpj_invalid_characters")

    dv1 = _cnpj_calc_dv(cleaned[:12], CNPJ_DV1_WEIGHTS)
    dv2 = _cnpj_calc_dv(cleaned[:12] + str(dv1), CNPJ_DV2_WEIGHTS)

    if int(cleaned[12]) != dv1 or int(cleaned[13]) != dv2:
        raise ValidationError("kartado.error.cnpj_invalid")

    return value


def generate_cnpj(alphanumeric=False):
    """Gera um CNPJ válido para uso em testes/seeds.

    :param alphanumeric: quando ``True``, sorteia letras maiúsculas além
        de dígitos nas 12 primeiras posições (formato IN RFB 2.229/2024).
        Quando ``False`` (padrão), gera apenas o formato numérico legado.
    """
    alphabet = string.digits + (string.ascii_uppercase if alphanumeric else "")
    base = "".join(random.choice(alphabet) for _ in range(12))
    dv1 = _cnpj_calc_dv(base, CNPJ_DV1_WEIGHTS)
    dv2 = _cnpj_calc_dv(base + str(dv1), CNPJ_DV2_WEIGHTS)
    cleaned = f"{base}{dv1}{dv2}"
    return (
        f"{cleaned[:2]}.{cleaned[2:5]}.{cleaned[5:8]}/"
        f"{cleaned[8:12]}-{cleaned[12:14]}"
    )
