import logging
import sys

from django.utils.text import compress_string

from helpers.json_parser import JSONRenderer

VIEWS_AND_ACTIONS_TO_COMPRESS = [
    ("OccurrenceTypeView", "list"),
    ("OccurrenceRecordView", "list"),
]


class LimitedSizeJSONRenderer(JSONRenderer):
    """Customizes the rest_framework_json_api JSON renderer so we can abide to lambda rules of never going over 6 MB"""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        SIX_MB_IN_BYTES = 6 * 1024 * 1024

        rendered_data = super().render(data, accepted_media_type, renderer_context)
        view = renderer_context.get("view", None) if renderer_context else None
        view_name = view.__class__.__name__ if view else ""
        action_name = view.action if view and hasattr(view, "action") else ""
        view_and_action = (view_name, action_name)

        final_data = (
            compress_string(rendered_data)
            if view_and_action in VIEWS_AND_ACTIONS_TO_COMPRESS
            else rendered_data
        )
        if sys.getsizeof(final_data) >= SIX_MB_IN_BYTES:
            req = renderer_context.get("request", None)
            if req:
                end = req.path
                user_name = req.user.get_full_name()
                method = req.method

                logging.error(
                    f"LimitedSizeJSONRenderer: {method} {end} by user '{user_name}' has reached the 6MB body size limit"
                )
            else:
                logging.error(
                    "LimitedSizeJSONRenderer: Unknown request has reached the 6MB body size limit"
                )

            return b'{"errors":[{"detail":"kartado.error.api.request_payload_cannot_exceed_six_megabytes"}]}'
        else:
            return rendered_data
