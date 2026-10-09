from __future__ import annotations


class NovelAIError(ValueError):
    """Public, secret-free failure with an explicit remote-outcome boundary."""

    def __init__(self, code: str, message: str, status: int = 502, *, unknown: bool = False):
        super().__init__(message)
        self.code = code
        self.status = status
        self.unknown = unknown

    def payload(self) -> dict[str, object]:
        return {"error_code": self.code, "error": str(self), "provider": "novelai",
                "remote_outcome_unknown": self.unknown}
