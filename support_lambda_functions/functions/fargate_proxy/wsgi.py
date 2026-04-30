"""
WSGI wrapper para deploy via Zappa.

Verifica o header X-Fargate-Async para identificar invocações assíncronas
(que chegam através da auto-invocação do Lambda) e executa o fluxo completo
diretamente, sem retornar ao API Gateway.
"""

import logging

from functions.fargate_proxy.handler import _process, lambda_handler


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "POST")
    path = environ.get("PATH_INFO", "/")

    if method == "GET" and path == "/":
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"status": "ok"}']

    content_length = int(environ.get("CONTENT_LENGTH", 0) or 0)
    body = (
        environ["wsgi.input"].read(content_length).decode("utf-8")
        if content_length
        else ""
    )

    headers = {
        key[5:].replace("_", "-").title(): value
        for key, value in environ.items()
        if key.startswith("HTTP_")
    }

    event = {
        "httpMethod": method,
        "path": path,
        "headers": headers,
        "body": body,
        "queryStringParameters": {},
    }

    if environ.get("HTTP_X_FARGATE_ASYNC") == "1":
        try:
            _process(event)
        except Exception as e:
            logging.error(f"[FargateProxy] Erro no processamento async: {e}")
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"status": "processing"}']

    result = lambda_handler(event, {})

    status_code = result.get("statusCode", 200)
    response_headers = list(
        (result.get("headers") or {"Content-Type": "application/json"}).items()
    )
    response_body = result.get("body", "")

    start_response(f"{status_code} OK", response_headers)
    return [
        response_body.encode("utf-8")
        if isinstance(response_body, str)
        else response_body
    ]
