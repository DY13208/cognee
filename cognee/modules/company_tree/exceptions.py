from typing import List, Optional

from fastapi import status

from cognee.exceptions import CogneeValidationError


class CompanyTreeWriteError(CogneeValidationError):
    """Rejected company-tree write: schema, identity, or completeness failed."""

    def __init__(
        self,
        message: str,
        missing: Optional[List[str]] = None,
        status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT,
    ):
        self.missing = missing or []
        super().__init__(
            message=message,
            name="CompanyTreeWriteError",
            status_code=status_code,
            log_level="WARNING",
        )
