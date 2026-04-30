import sentry_sdk
from django.http import HttpRequest, JsonResponse
from django_ratelimit.exceptions import Ratelimited
from rest_framework.request import Request

# import mixin correctly
try:
    from django.utils.deprecation import MiddlewareMixin
except ImportError:
    MiddlewareMixin = object

# makes this thread-safe
from threading import local

_thread_locals = local()


def get_current_request(default_to_empty_request=False):
    return getattr(
        _thread_locals,
        "request",
        Request(request=HttpRequest()) if default_to_empty_request else None,
    )


def get_current_user():
    request = get_current_request()
    if request:
        return getattr(request, "user", None)
    return None


class ActionLogMiddleware(MiddlewareMixin):
    """Makes request available to this app signals."""

    def process_request(self, request):
        _thread_locals.request = request

    def process_response(self, request, response):
        try:
            del _thread_locals.request
        except Exception:
            pass
        return response

    def process_exception(self, request, exception):
        try:
            del _thread_locals.request
        except Exception:
            pass


def ratelimit_exceeded_view(request, exception):
    if isinstance(exception, Ratelimited):
        sentry_sdk.capture_exception(exception)
        return JsonResponse({"detail": "Too many requests"}, status=429)
    return JsonResponse({"detail": "Forbidden"}, status=403)


class RawRequestBodyMiddleware:
    """
    Middleware to cache the raw request body for MultipleDailyReport operations.

    This middleware reads the raw body of the request and caches it as request.raw_body
    for both creation (POST) and editing (PATCH) of MultipleDailyReport instances.
    It also supports MultipleDailyReportFile operations.

    The middleware acts on:
    - POST requests to '/MultipleDailyReport/' (creation)
    - PATCH requests to '/MultipleDailyReport/{id}/' (edition)
    - POST requests to '/MultipleDailyReportFile/' (file upload)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Set a default empty value for raw_body
        request.raw_body = b""

        # Check if this is a MultipleDailyReport operation
        is_multiple_daily_report_operation = (
            # Creation: POST to collection URL
            (request.path == "/MultipleDailyReport/" and request.method == "POST")
            or
            # Edition: PATCH to specific instance URL
            (
                request.path.startswith("/MultipleDailyReport/")
                and request.path.endswith("/")
                and request.method == "PATCH"
            )
            or
            # File upload: POST to file collection URL
            (request.path == "/MultipleDailyReportFile/" and request.method == "POST")
        )

        if is_multiple_daily_report_operation:
            content_type = request.content_type.lower()
            if content_type in ("application/json", "application/vnd.api+json"):
                try:
                    request.raw_body = request.body
                except Exception:
                    # In case of an error, the default empty byte string is already set.
                    pass

        response = self.get_response(request)
        return response
