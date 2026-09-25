from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ApiKeyScheme(OpenApiAuthenticationExtension):
    target_class = "merchants.authentication.ApiKeyAuthentication"
    name = "ApiKeyAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "X-API-Key", "description": "Your Gaxtron API key."}


def only_v1(endpoints, **kwargs):
    """Keep the legacy unversioned gateway routes out of the public developer docs."""
    return [e for e in endpoints if e[0].startswith("/v1/")]
