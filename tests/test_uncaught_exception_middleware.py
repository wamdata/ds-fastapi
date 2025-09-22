import logging

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from ds_fastapi.UncaughtExceptionMiddleware import UncaughtExceptionMiddleware


class ErrorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/middleware-error":
            raise ValueError("Middleware error!")
        return await call_next(request)


def create_app(debug: bool = False) -> FastAPI:
    app = FastAPI(debug=debug)
    app.add_middleware(
        UncaughtExceptionMiddleware,
        logger=logging.getLogger("test"),
        debug=debug,
    )

    @app.get("/boom")
    def boom():
        raise RuntimeError("Boom!")

    @app.get("/ok")
    def ok():
        return {"ok": True}

    return app


def create_app_with_error_middleware(debug: bool = False) -> FastAPI:
    app = FastAPI(debug=debug)
    app.add_middleware(ErrorMiddleware)
    app.add_middleware(
        UncaughtExceptionMiddleware,
        logger=logging.getLogger("test"),
        debug=debug,
    )

    @app.get("/middleware-error")
    def middleware_error():
        return {"should": "not reach this"}

    @app.get("/ok")
    def ok():
        return {"ok": True}

    return app


def create_app_with_wrong_middleware_order(debug: bool = False) -> FastAPI:
    app = FastAPI(debug=debug)
    app.add_middleware(
        UncaughtExceptionMiddleware,
        logger=logging.getLogger("test"),
        debug=debug,
    )
    app.add_middleware(ErrorMiddleware)

    @app.get("/middleware-error")
    def middleware_error():
        return {"should": "not reach this"}

    @app.get("/ok")
    def ok():
        return {"ok": True}

    return app


def test_middleware_catches_uncaught_exceptions_and_hides_traceback_by_default(
    caplog: pytest.LogCaptureFixture,
):
    app = create_app(debug=False)
    client = TestClient(app)

    with caplog.at_level(logging.ERROR):
        r = client.get("/boom")

    assert r.status_code == 500
    data = r.json()
    assert (
        data["detail"]["message"]
        == "Unknown Internal Server Error. Please contact support and provide them with the details of your request."
    )
    assert "traceback" not in data["detail"]

    for record in caplog.records:
        assert record.levelname == "ERROR"
        assert record.exc_info is not None
        assert record.exc_text is not None
        assert record.exc_text.startswith("Traceback (most recent call last):")
        assert record.exc_text.endswith("RuntimeError: Boom!")


def test_middleware_includes_traceback_when_debug_true():
    app = create_app(debug=True)
    client = TestClient(app)

    r = client.get("/boom")
    assert r.status_code == 500
    data = r.json()
    assert data["detail"]["message"] == "Boom!"
    assert isinstance(data["detail"].get("traceback"), list)


def test_middleware_catches_exceptions_from_other_middleware():
    app = create_app_with_error_middleware(debug=False)
    client = TestClient(app)

    r = client.get("/middleware-error")
    assert r.status_code == 500
    data = r.json()
    assert (
        data["detail"]["message"]
        == "Unknown Internal Server Error. Please contact support and provide them with the details of your request."
    )
    assert "traceback" not in data["detail"]


def test_middleware_with_wrong_order_cannot_catch_exceptions():
    app = create_app_with_wrong_middleware_order(debug=False)
    client = TestClient(app)

    # When the middleware order is wrong, the ErrorMiddleware runs after
    # UncaughtExceptionMiddleware, so the exception won't be caught
    try:
        client.get("/middleware-error")
        # If we get here, the exception wasn't raised (unexpected)
        raise AssertionError("Expected ValueError to be raised")
    except ValueError as e:
        assert str(e) == "Middleware error!"


def test_ok_endpoint_passes_through():
    app = create_app(debug=False)
    client = TestClient(app)

    r = client.get("/ok")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
