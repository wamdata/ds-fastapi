import logging

from fastapi import Depends
from fastapi.testclient import TestClient

from ds_fastapi import EnhancedFastAPI, UncaughtExceptionMiddleware


class _AuthDep:
    def __call__(self):
        return True
    
    # Document dependency errors so EnhancedFastAPI can merge into OpenAPI
    responses = {401: {"description": "Unauthorized"}}


_auth_dep = _AuthDep()


def create_app(debug: bool = False) -> EnhancedFastAPI:
    app = EnhancedFastAPI(debug=debug)

    # Add exception middleware so 500 responses follow the expected shape
    app.add_middleware(
        UncaughtExceptionMiddleware,
        logger=logging.getLogger("test"),
        debug=debug,
    )

    @app.get("/ping", dependencies=[Depends(_auth_dep)])
    def ping():
        return {"pong": True}

    return app


def test_openapi_includes_dependency_responses_and_500_schema():
    app = create_app(debug=False)
    client = TestClient(app)

    schema = client.get("/openapi.json").json()

    # Components include our InternalServerError schema
    assert "InternalServerError" in schema["components"]["schemas"], (
        "InternalServerError schema missing"
    )

    # /ping operation contains dependency response 401 and generic 500
    ping_get = schema["paths"]["/ping"]["get"]
    assert "responses" in ping_get
    assert "401" in ping_get["responses"], "Dependency 401 response missing"
    assert "500" in ping_get["responses"], "Generic 500 response missing"
