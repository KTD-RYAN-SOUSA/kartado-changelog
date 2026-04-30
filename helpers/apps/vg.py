import base64
import json
import uuid
from datetime import datetime

import requests
from django.conf import settings
from django.utils import timezone

from apps.occurrence_records.models import OccurrenceRecord
from apps.templates.models import Log
from helpers.strings import clean_latin_string


class VGSync:
    def __init__(self, record, retry=False):
        self.message = ""
        self.retry = retry
        self.record = record
        self.measure_translation = {
            106: ["metro cubico", "m3", "106"],
            107: ["litro", "l", "107"],
            108: ["quilograma", "quilo", "kg", "108"],
            109: ["tonelada", "ton", "t", "109"],
            110: ["unidade", "und", "110"],
        }

    def get_measure_unit(self):
        form_data_unit = self.record.form_data.get("unit", False)
        if form_data_unit:
            if (
                isinstance(form_data_unit, int)
                and form_data_unit in self.measure_translation.keys()
            ):
                return form_data_unit
            if isinstance(form_data_unit, str):
                possible_values = [
                    key
                    for key, value in self.measure_translation.items()
                    if clean_latin_string(form_data_unit).lower() in value
                ]
                if possible_values:
                    return possible_values[0]

        return 108

    def send_post_request(self, access_token, access_type):
        residuos_url = "{}/{}/residue-generations".format(self.base_url, self.vg_code)

        residuo_uuid = self.record.form_data.get("code_residuo", "")
        try:
            obj_uuid = uuid.UUID(residuo_uuid)
            obj = OccurrenceRecord.objects.get(pk=obj_uuid)
        except Exception:
            pass
        else:
            residuo_uuid = obj.form_data.get("code", "")

        # Create url
        url = "{}/#/SharedLink/OccurrenceRecord/{}/show?company={}".format(
            settings.FRONTEND_URL, str(self.record.uuid), str(self.company.pk)
        )

        residuos_data = {
            "Date": self.record.created_at.strftime("%Y-%m-%d"),
            "ResidueCode": residuo_uuid,
            "Quantity": self.record.form_data.get("amount", 0),
            "MeasureUnitId": self.get_measure_unit(),
            "AdditionalInformations": [
                {
                    "Property": "Integração Kartado",
                    "Value": self.record.form_data.get("record_source", "DESCONHECIDO"),
                },
                {
                    "Property": "Usuário Kartado",
                    "Value": self.record.created_by.get_full_name()
                    if self.record.created_by
                    else "",
                },
                {"Property": "URL Kartado", "Value": url},
            ],
        }

        source_area_code = self.record.form_data.get("source_area_code", False)
        if source_area_code:
            residuos_data = {**residuos_data, "AreaCode": source_area_code}

        residuos_headers = {
            "Authorization": access_type + " " + access_token,
            "Content-Type": "application/json",
            "Organization": str(self.org_code),
        }

        request_data = {
            "url": residuos_url,
            "headers": residuos_headers,
            "data": json.dumps(residuos_data),
        }

        send_residuos_request = requests.post(**request_data)

        try:
            residuos_json = send_residuos_request.json()
        except Exception:
            residuos_json = {}

        request = {**request_data, "type": "POST"}
        response = {
            "status_code": send_residuos_request.status_code,
            "body": residuos_json,
        }

        if (
            (send_residuos_request.status_code == 200)
            and isinstance(residuos_json, dict)
            and ("Id" in residuos_json)
        ):
            self.create_log(
                reason="Success posting VG residuos",
                request=request,
                response=response,
            )
            return residuos_json
        else:
            self.message = "Erro na requisição com a VG."
            self.create_log(
                reason="Error posting VG residuos",
                request=request,
                response=response,
            )
            if (
                isinstance(residuos_json, list)
                and residuos_json
                and isinstance(residuos_json[0], dict)
                and "Message" in residuos_json[0]
            ):
                self.message = residuos_json[0]["Message"]
            return False

    def get_token(self):
        token = "{}:{}".format(self.login, self.pwd)
        token_bytes = token.encode("ascii")
        base64_bytes = base64.b64encode(token_bytes)
        base64_token = base64_bytes.decode("ascii")

        token_headers = {
            "Authorization": "Basic " + base64_token,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        token_params = {
            "client_id": self.login,
            "grant_type": "client_credentials",
        }

        request_data = {
            "url": self.token_url,
            "headers": token_headers,
            "data": token_params,
        }

        token_request = requests.post(**request_data)

        try:
            token_json = token_request.json()
        except Exception:
            token_json = {}

        request = {**request_data, "type": "POST"}
        response = {
            "status_code": token_request.status_code,
            "body": token_json,
        }

        if (
            (token_request.status_code == 200)
            and isinstance(token_json, dict)
            and ("access_token" in token_json)
            and ("token_type" in token_json)
        ):
            self.create_log(
                reason="Success getting VG token",
                request=request,
                response=response,
            )
            return token_json

        self.create_log(
            reason="Error getting VG token", request=request, response=response
        )
        self.message = "Erro na obtenção do token."
        return False

    def create_log(self, reason, request=None, response=None):
        result = {
            "type": "Engie VG API Call",
            "obj_uuid": str(self.record.pk),
            "request": request,
            "response": response,
            "result": reason,
            "is_retry": self.retry,
        }

        Log.objects.create(
            description=result, date=timezone.now(), company=self.company
        )
        return True

    def process_sync(self):
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.token_url = settings.VG_TOKEN
            self.pwd = settings.VG_PWD
            self.login = settings.VG_LOGIN
            self.base_url = settings.VG_BASE_URL
            self.company = self.record.company
            self.vg_code = self.company.metadata["vg_sync"]["vg_code"]
            self.org_code = self.company.metadata["vg_sync"]["org_code"]
        except Exception:
            self.create_log(reason="Error getting VG data")
            self.message = "Dados da sincronização VG não configurados."
        else:
            token = self.get_token()
            if token:
                access_token = token.get("access_token", "")
                access_type = token.get("token_type", "")

                post_request = self.send_post_request(access_token, access_type)

                if post_request:
                    residuo_id = post_request.get("Id", "")
                    self.record.editable = False
                    self.record.form_data["vg_integration"] = {
                        "id": residuo_id,
                        "timestamp": self.timestamp,
                        "success": True,
                        "message": "",
                    }
                    return self.record

        self.record.form_data["vg_integration"] = {
            "id": None,
            "timestamp": self.timestamp,
            "success": False,
            "message": self.message,
        }
        return self.record
