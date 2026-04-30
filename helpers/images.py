from PIL import Image

from helpers.dates import utc_to_local
from helpers.strings import deg_to_dms, get_direction_name, get_str_from_xyz


def build_text_dict(file_obj, watermark_fields, use_file_location, company):
    # Add watermark to image
    reporting = file_obj.reporting
    # Number
    number = reporting.number
    # Photo Date
    if file_obj.datetime:
        photo_date = file_obj.datetime
    else:
        photo_date = file_obj.uploaded_at
    photo_date = utc_to_local(photo_date)
    # Direction
    direction = reporting.direction
    direction_final = get_direction_name(company, direction)
    # Road name
    road_name = reporting.road_name
    # km
    if use_file_location and file_obj.km:
        km = format(round(float(file_obj.km), 3), ".3f").replace(".", "+")
    else:
        km = format(round(float(reporting.km), 3), ".3f").replace(".", "+")
    # Longitude and Latitude
    if use_file_location and file_obj.point:
        point = file_obj.point
    else:
        point = reporting.point
    # Status
    status = reporting.status.name if reporting.status else ""
    # Classe
    classe = reporting.occurrence_type.name if reporting.occurrence_type else ""
    # Data de execução
    executed_at = (
        utc_to_local(reporting.executed_at) if reporting.executed_at is not None else ""
    )
    # Observations
    if "notes" in reporting.form_data:
        notes = str(reporting.form_data["notes"])
    else:
        notes = ""

    text_dict = {}
    if "date" in watermark_fields:
        text_dict["Data da imagem"] = photo_date.strftime("%d/%m/%Y")
    if "date_and_hour" in watermark_fields:
        text_dict["Data da imagem"] = photo_date.strftime("%d/%m/%Y, %H:%M:%S")
    if "executed_at" in watermark_fields:
        text_dict["Executado em"] = (
            executed_at.strftime("%d/%m/%Y") if executed_at != "" else "-"
        )
    if "executed_at_with_hour" in watermark_fields:
        text_dict["Executado em"] = (
            executed_at.strftime("%d/%m/%Y, %H:%M:%S") if executed_at != "" else "-"
        )
    if "road" in watermark_fields:
        text_dict["none1"] = road_name + " " + km
    if "coordinates_xyz" in watermark_fields:
        text_dict["none2"] = get_str_from_xyz(point)
    if "coordinates_dec" in watermark_fields:
        longitude = round(point.coords[0], 6)
        latitude = round(point.coords[1], 6)
        text_dict["none2"] = "Lat: {:.6f} Lng: {:.6f}".format(latitude, longitude)
    if "coordinates_dms" in watermark_fields:
        longitude = deg_to_dms(round(point.coords[0], 6), coord="lon")
        latitude = deg_to_dms(round(point.coords[1], 6))
        text_dict["none2"] = latitude + " " + longitude
    if "direction" in watermark_fields:
        text_dict["Sentido"] = direction_final
    if "number" in watermark_fields:
        text_dict["Serial"] = number
    if "status" in watermark_fields:
        text_dict["Status"] = status
    if "classe" in watermark_fields:
        text_dict["Classe"] = classe
    # keep notes the last one
    if "notes" in watermark_fields:
        text_dict["Observações"] = notes

    return text_dict


def remove_white_background(image_path, output_path=None):
    img = Image.open(image_path)
    img = img.convert("RGBA")
    datas = img.getdata()
    new_data = []
    for item in datas:
        if item[0] == 255 and item[1] == 255 and item[2] == 255:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    img.putdata(new_data)

    # Salve a imagem com fundo transparente
    if output_path is None:
        path_split: list = image_path.split(".")
        extension_file = path_split[-1]
        path_split.insert(-1, "_transparent")
        output_path = f"{('').join(path_split[0:-1])}.{extension_file}"

    img.save(f"{output_path}", "PNG")

    return output_path
