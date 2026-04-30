from datetime import datetime, timedelta

import pytz
import requests
from rest_framework import status

from apps.templates.models import Log
from RoadLabsAPI.settings import credentials


def hidro_api(dam, date):
    fetch_date = date.astimezone(pytz.timezone("UTC")) - timedelta(hours=3)
    max_tries = 10
    response = None
    error = None
    while max_tries > 0:
        data = {
            "sistema": "KARTADO",
            "usina": dam,
            "dataHora": fetch_date.strftime("%d/%m/%Y %H:00"),
        }
        try:
            request = requests.post(
                url=credentials.HIDRO_URL,
                json=data,
                auth=requests.auth.HTTPBasicAuth(
                    credentials.HIDRO_USERNAME, credentials.HIDRO_PWD
                ),
            )
            request.raise_for_status()
        except Exception as e:
            request = None
            response = None
            error = str(e)
            break

        if request.status_code == status.HTTP_200_OK:
            response = request.json()
            if response["codResultado"] != "0":
                break
        else:
            response = None
            error = "Response Status Code " + str(request.status_code)
            break

        max_tries -= 1
        if max_tries != 0:
            fetch_date = fetch_date - timedelta(hours=1)

    result = {
        "type": "Engie Hidrologia API Call",
        "request": {"url": credentials.HIDRO_URL, "type": "POST", "body": data},
        "response": {
            "status_code": request.status_code if request else "Error",
            "body": response,
            "headers": dict(request.headers) if request else "Error",
        },
        "error": error,
    }

    Log.objects.create(description=result, date=datetime.now().replace(tzinfo=pytz.UTC))

    if response and int(response["codResultado"]) > 0:
        info = response["NivelReservatorioDataHoraLista"][0]
    else:
        info = None

    return {
        "response": info,
        "tryFrom": date.strftime("%d/%m/%Y %H:00"),
        "tryUntil": fetch_date.strftime("%d/%m/%Y %H:00"),
        "error": error,
    }
