from rest_framework import status
from rest_framework.response import Response
from rest_framework_json_api.exceptions import exception_handler

from apps.templates.models import ExportRequest
from apps.templates.notifications import send_email_export_request


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if context["view"].request._request.method == "PATCH":
        model_obj = None
        try:
            model_obj = context["view"].serializer_class().Meta.model
        except Exception:
            pass

        if ExportRequest == model_obj:
            try:
                export_request_id = context["kwargs"]["pk"]
                obj = ExportRequest.objects.get(pk=export_request_id)
            except Exception:
                pass
            else:
                obj.error = True
                obj.save()
                send_email_export_request(obj)

    return response


def error_message(error_number, string):
    codes = {
        str(value): str(name)
        for name, value in status.__dict__.items()
        if "HTTP" in name
    }

    try:
        codes[str(error_number)]
    except KeyError:
        return Response({"attributes": {"status": "Erro! Http status não encontrado."}})

    return Response(
        data=[
            {
                "detail": string,
                "source": {"pointer": "/data"},
                "status": error_number,
            }
        ],
        status=error_number,
    )
