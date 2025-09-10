from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.logger import logger
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.types import ASGIApp

from .UncaughtExceptionMiddleware import UncaughtExceptionMiddleware


class EnhancedFastAPI(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        # This will add the UncaughtExceptionMiddleware to the end of the
        # middleware stack just before the middleware stack is instantiated
        # making it the outermost middleware
        self.add_middleware(
            UncaughtExceptionMiddleware, logger=logger, debug=self.debug
        )

        return super().build_middleware_stack()

    def _add_dependencies_responses_to_operations(self, openapi_schema: dict[str, Any]):
        """Add dependency responses to operations in the OpenAPI schema."""

        def add_dependency_responses(
            dependency: Dependant, openapi_operation: dict[str, Any]
        ):
            if dependency.call is not None and hasattr(dependency.call, "responses"):
                dependency_responses = dependency.call.responses  # type: ignore
                for status_code, dependency_response in dependency_responses.items():
                    status_code = str(status_code)
                    dependency_response_copy = dependency_response.copy()
                    if "model" in dependency_response_copy:
                        model = dependency_response_copy.pop("model")
                        if issubclass(model, BaseModel):
                            dependency_response_copy["content"] = {
                                "application/json": {
                                    "schema": model.model_json_schema()
                                }
                            }
                        else:
                            raise ValueError(
                                f"Invalid model: {model} is not a pydantic model"
                            )
                    if status_code not in openapi_operation["responses"]:
                        openapi_operation["responses"][status_code] = (
                            dependency_response_copy
                        )
                    else:
                        openapi_operation["responses"][status_code] = (
                            self._merge_openapi_responses(
                                [
                                    openapi_operation["responses"][status_code],
                                    dependency_response_copy,
                                ],
                            )
                        )

            for sub_dep in dependency.dependencies:
                add_dependency_responses(sub_dep, openapi_operation)

        for route in self.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                openapi_operation = openapi_schema["paths"][route.path][method.lower()]
                for dependency in route.dependant.dependencies:
                    add_dependency_responses(
                        dependency=dependency,
                        openapi_operation=openapi_operation,
                    )

    def _add_500_response_to_operations(self, openapi_schema: dict[str, Any]) -> None:
        """Add 500 error response to all operations in the OpenAPI schema."""

        # Define the InternalServerError schema component
        openapi_schema["components"]["schemas"]["InternalServerError"] = {
            "type": "object",
            "properties": {
                "detail": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "examples": [
                                "Unknown Internal Server Error. "
                                + "Please contact support and provide them with the "
                                + "details of your request."
                            ],
                        },
                        "traceback": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Only included when debug=True",
                        },
                    },
                    "required": ["message"],
                },
                "required": ["detail"],
            },
        }

        # Add 500 response to all operations
        for path in openapi_schema["paths"].values():
            for operation in path.values():
                if "responses" not in operation:
                    operation["responses"] = {}
                if "500" not in operation["responses"]:
                    operation["responses"]["500"] = {
                        "description": "Internal Server Error",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/InternalServerError"
                                }
                            }
                        },
                    }

    def openapi(self):
        """
        Override the default openapi() method to add custom error responses.
        """
        if self.openapi_schema:
            return self.openapi_schema
        openapi_schema = super().openapi()

        # Define the error schema component if it doesn't exist
        if "components" not in openapi_schema:
            openapi_schema["components"] = {}
        if "schemas" not in openapi_schema["components"]:
            openapi_schema["components"]["schemas"] = {}

        # Check if HTTPError schema already exists
        if "InternalServerError" in openapi_schema["components"]["schemas"]:
            raise ValueError(
                "HTTPError schema is already defined in OpenAPI components"
            )

        # Remove null from anyof and oneOf for query and path parameters
        for path in openapi_schema["paths"].values():
            for operation in path.values():
                if "parameters" in operation:
                    for param in operation.get("parameters", []):
                        if param.get("in") in ["query", "path"]:
                            schema = param.get("schema", {})
                            schema_key = None
                            if "anyOf" in schema:
                                schema_key = "anyOf"
                            elif "oneOf" in schema:
                                schema_key = "oneOf"

                            if schema_key is not None:
                                filtered = [
                                    s
                                    for s in schema[schema_key]
                                    if s.get("type") != "null"
                                ]
                                if len(filtered) == 1:
                                    del param["schema"][schema_key]
                                    param["schema"].update(filtered[0])
                                else:
                                    param["schema"][schema_key] = filtered

        self._add_dependencies_responses_to_operations(openapi_schema)
        self._add_500_response_to_operations(openapi_schema)

        self.openapi_schema = openapi_schema
        return self.openapi_schema

    def _merge_openapi_responses(
        self, responses: list[dict[Any, Any]]
    ) -> dict[str, Any]:
        """
        Merge two OpenAPI response specs into one, following OpenAPI spec rules.
        Handles all response object fields with proper merging semantics.
        """
        from collections import defaultdict

        merged_description: list[str] = []
        content_map: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"schemas": [], "examples": {}}
        )

        # Process both responses
        for response in responses:
            # Merge descriptions
            desc = response.get("description")
            if desc:
                merged_description.append(desc)

            # Headers merging not supported
            if response.get("headers"):
                raise NotImplementedError("Merging headers is not supported")

            # Links merging not supported
            if response.get("links"):
                raise NotImplementedError("Merging links is not supported")

            # Merge content
            content = response.get("content", {})
            for content_type, content_def in content.items():
                # Handle schema
                schema = content_def.get("schema", {})
                if schema not in content_map[content_type]["schemas"]:
                    content_map[content_type]["schemas"].append(schema)

                # Handle examples
                example = content_def.get("example")
                if example:
                    raise NotImplementedError("Merging example is not supported")

                # Add suffix on conflicting example names
                examples = content_def.get("examples", {})
                for example_name, example in examples.items():
                    if example_name in content_map[content_type]["examples"]:
                        i = 1
                        while (
                            f"{example_name}_{i}"
                            in content_map[content_type]["examples"]
                        ):
                            i += 1
                        content_map[content_type]["examples"][f"{example_name}_{i}"] = (
                            example
                        )
                    else:
                        content_map[content_type]["examples"][example_name] = example

                # Handle encoding
                encoding = content_def.get("encoding", {})
                if encoding:
                    raise NotImplementedError("Merging encoding is not supported")

        # Build final merged response
        merged_response: dict[str, Any] = {
            "description": " / ".join(merged_description) or "Successful response",
        }

        for content_type, details in content_map.items():
            entry = {}

            # Use `oneOf` if more than one schema, else just use the single schema
            schemas = details["schemas"]
            if len(schemas) == 1:
                entry["schema"] = schemas[0]
            elif len(schemas) > 1:
                entry["schema"] = {"oneOf": schemas}

            # Add examples if available
            if details["examples"]:
                entry["examples"] = details["examples"]

            merged_response.setdefault("content", {})
            merged_response["content"][content_type] = entry

        return merged_response
