import traceback
from logging import Logger

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class UncaughtExceptionMiddleware:
    """
    Middleware for Starlette/FastAPI applications that catches all uncaught exceptions
    during HTTP request processing. It logs the exception (if a logger is provided)
    and returns a standardized JSON error response with status code 500.

    Typical usage:
        from ds_fastapi.UncaughtExceptionMiddleware import UncaughtExceptionMiddleware

        app = FastAPI()
        app.add_middleware(UncaughtExceptionMiddleware, logger=my_logger, debug=True)

    Middleware Order:
        Middleware added with `app.add_middleware` forms a stack:
            - The last middleware added is the outermost.
            - The first middleware added is the innermost.
            - On requests: outermost runs first.
            - On responses: outermost runs last.

        To ensure all exceptions are caught, this middleware should be added last:

            app.add_middleware(OtherMiddleware)
            app.add_middleware(UncaughtExceptionMiddleware, logger=my_logger, debug=True)

    Args:
        app (ASGIApp): The ASGI application.
        logger (Logger, optional): Logger instance for error logging. Defaults to None.
        debug (bool, optional): If True, include exception details and traceback
            in the response. Defaults to False.
    """

    def __init__(
        self,
        app: ASGIApp,
        logger: Logger | None = None,
        debug: bool = False,
    ):
        self.app = app
        self.debug = debug
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self.app(scope, receive, send)
        except Exception as err:
            if self.logger is not None:
                self.logger.error(msg=f"Uncaught Exception: {err}", exc_info=True)

            detail: dict[str, str | list[str]] = {
                "message": (
                    "Unknown Internal Server Error. "
                    "Please contact support and provide them with "
                    "the details of your request."
                ),
            }

            if self.debug:
                detail["message"] = str(err)
                detail["traceback"] = traceback.format_exception(err)

            response = JSONResponse(content={"detail": detail}, status_code=500)
            await response(scope, receive, send)
