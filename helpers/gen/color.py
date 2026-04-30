import random


def get_random_color_hex():
    # Gerar três valores aleatórios entre 0 e 255 para representar os componentes RGB
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)

    # Formatar os valores como hexadecimal e concatenar para obter o código de cor completo
    cor_hex = "#{:02x}{:02x}{:02x}".format(r, g, b)

    return cor_hex
