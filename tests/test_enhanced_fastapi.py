from fastapi import Depends
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ds_fastapi import EnhancedFastAPI


class ErrorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/middleware-error":
            raise ValueError("Middleware error!")
        return await call_next(request)


class _AuthDep:
    def __call__(self):
        return True

    # Document dependency errors so EnhancedFastAPI can merge into OpenAPI
    responses = {401: {"description": "Unauthorized"}}


_auth_dep = _AuthDep()


def create_app(debug: bool = False) -> EnhancedFastAPI:
    app = EnhancedFastAPI(debug=debug)

    app.add_middleware(ErrorMiddleware)

    @app.get("/ping", dependencies=[Depends(_auth_dep)])
    def ping():
        return {"pong": True}

    @app.get("/boom")
    def boom():
        raise RuntimeError("Boom!")

    @app.get("/middleware-error")
    def middleware_error():
        return {"should": "not reach this"}

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

    # /boom operation contains generic 500
    boom_get = schema["paths"]["/boom"]["get"]
    assert "responses" in boom_get
    assert "500" in boom_get["responses"], "Generic 500 response missing"


def test_UncaughtExceptionMiddleware_is_included_and_works():
    app = create_app()
    client = TestClient(app)

    r = client.get("/boom")
    assert r.status_code == 500
    data = r.json()
    assert (
        data["error"]["message"]
        == "Unknown Internal Server Error. Please contact support and provide them with the details of your request."
    )
    assert "traceback" not in data["error"]

    r = client.get("/middleware-error")
    assert r.status_code == 500
    data = r.json()
    assert (
        data["error"]["message"]
        == "Unknown Internal Server Error. Please contact support and provide them with the details of your request."
    )
    assert "traceback" not in data["error"]
