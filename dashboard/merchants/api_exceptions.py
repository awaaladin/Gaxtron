"""
Normalizes DRF error responses to the same {"detail": ...} shape FastAPI used, since
frontend/js/api.js and the Android app's error parsing both expect it: a string detail,
or (for validation errors) a list of {"msg": "..."} objects.
"""
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and "detail" in data and not isinstance(data["detail"], list):
        response.data = {"detail": str(data["detail"])}
        return response

    # Serializer validation errors: {"field": ["msg", ...], ...} -> {"detail": [{"msg": "..."}]}
    if isinstance(data, dict):
        messages = []
        for field, errors in data.items():
            errors = errors if isinstance(errors, list) else [errors]
            for err in errors:
                messages.append({"msg": f"{field}: {err}" if field != "non_field_errors" else str(err)})
        response.data = {"detail": messages or [{"msg": "Validation failed"}]}
    return response
