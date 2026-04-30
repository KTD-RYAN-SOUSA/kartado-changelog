import re


def remove_leading_zero(number: str) -> str:
    """
    Removes all leading zeros from a number.

    Args:
        number (str): The number to remove the leading zeros from.

    Returns:
        str: The number with all leading zeros removed.
    """
    # Remove all leading zeros
    return number.lstrip("0")


def format_mobile_number_brazilin(phone_number: str) -> str:
    """
    Formats a Brazilian phone number.

    Args:
        phone_number (str): The phone number to format.

    Returns:
        str: The formatted phone number.

    """
    # Remove characters that are not digits
    cleaned_number = remove_leading_zero(re.sub(r"\D", "", str(phone_number)))

    if len(cleaned_number) != 11:
        return phone_number

    # Apply the mask (xx) x xxxx-xxxx
    formatted_number = (
        f"({cleaned_number[:2]}) {cleaned_number[2:7]}-{cleaned_number[7:]}"
    )

    return formatted_number


def format_phone_number_brazilin(phone_number: str) -> str:
    """
    Formats a Brazilian phone number.

    Args:
        phone_number (str): The phone number to format.

    Returns:
        str: The formatted phone number.

    """
    # Remove characters that are not digits
    cleaned_number = remove_leading_zero(re.sub(r"\D", "", str(phone_number)))
    cleaned_number = cleaned_number.lstrip("0")

    if len(cleaned_number) != 10:
        return phone_number

    # Apply the mask (xx) x xxxx-xxxx
    formatted_number = (
        f"({cleaned_number[:2]}) {cleaned_number[2:6]}-{cleaned_number[6:]}"
    )

    return formatted_number


def format_cpf_brazilin(cpf: str) -> str:
    """
    Formats a Brazilian CPF.

    Args:
        cpf (str): The CPF to format.

    Returns:
        str: The formatted CPF.

    """
    # Remove characters that are not digits
    cleaned_number = re.sub(r"\D", "", str(cpf))

    if len(cleaned_number) != 11:
        return cpf

    # Apply the mask xxx.xxx.xxx-xx
    formatted_number = f"{cleaned_number[0:3]}.{cleaned_number[3:6]}.{cleaned_number[6:9]}-{cleaned_number[9:]}"

    return formatted_number
