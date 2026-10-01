class AngelError(Exception):
    code = "angel_error"
    http_status = 500

    def __init__(self, message: str = "", details: dict | None = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details = details or {}


class ValidationError(AngelError):
    code = "validation_error"
    http_status = 422


class PermissionDenied(AngelError):
    code = "permission_denied"
    http_status = 403


class ConfirmationRequired(AngelError):
    code = "confirmation_required"
    http_status = 409


class NotFound(AngelError):
    code = "not_found"
    http_status = 404


class Conflict(AngelError):
    code = "conflict"
    http_status = 409


class ToolExecutionError(AngelError):
    code = "tool_execution_error"
    http_status = 500


class LLMError(AngelError):
    code = "llm_error"
    http_status = 502


class ExternalServiceError(AngelError):
    code = "external_service_error"
    http_status = 502


class DatabaseError(AngelError):
    code = "database_error"
    http_status = 500