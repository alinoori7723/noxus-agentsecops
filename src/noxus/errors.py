from __future__ import annotations


class SchemaContractError(Exception):
    def __init__(self, message: str, *, raw_excerpt: str | None = None) -> None:
        super().__init__(message)
        self.raw_excerpt = raw_excerpt
