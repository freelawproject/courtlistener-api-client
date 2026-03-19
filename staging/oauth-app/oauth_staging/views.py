"""Custom views for the staging OAuth app.

Provides a token introspection endpoint that includes the user's
CL API token in the response. This is how the MCP server exchanges
an OAuth access token for the CL API token it needs to call the
CourtListener API.
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from oauth2_provider.models import AccessToken


@csrf_exempt
@require_POST
def introspect(request):
    """RFC 7662 token introspection with CL API token extension.

    The MCP server calls this endpoint to validate an OAuth access
    token and retrieve the associated CL API token.

    Request::

        POST /oauth/introspect/
        Content-Type: application/x-www-form-urlencoded

        token=<oauth-access-token>

    Response (active token)::

        {
            "active": true,
            "username": "alice",
            "scope": "read write",
            "cl_api_token": "abc123..."
        }

    Response (inactive/invalid token)::

        {"active": false}
    """
    token_value = request.POST.get("token")
    if not token_value:
        return JsonResponse({"active": False})

    try:
        access_token = AccessToken.objects.select_related(
            "user__cl_api_token"
        ).get(token=token_value)
    except AccessToken.DoesNotExist:
        return JsonResponse({"active": False})

    if access_token.is_expired():
        return JsonResponse({"active": False})

    response = {
        "active": True,
        "username": access_token.user.username,
        "scope": access_token.scope,
    }

    # Include the user's CL API token so the MCP server can
    # use it for upstream API calls.
    try:
        cl_token = access_token.user.cl_api_token
        response["cl_api_token"] = cl_token.token
    except Exception:
        # User hasn't set up a CL API token yet.
        pass

    return JsonResponse(response)
