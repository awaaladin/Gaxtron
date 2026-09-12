from django.conf import settings


def gaxtron(request):
    """Makes the FastAPI public URL available to every template (shared CSS/JS assets live there)."""
    return {"FASTAPI_PUBLIC_URL": settings.PUBLIC_BASE_URL}
