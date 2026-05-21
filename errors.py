import logging
from dataclasses import dataclass
from typing import Optional

from litellm import APIError, BadRequestError, InternalServerError

logger = logging.getLogger(__name__)


@dataclass
class ProviderErrorInfo:
    """Internal error classification for logging and debugging."""
    message: str
    status_code: int
    code: Optional[str] = None
    param: Optional[str] = None


def raise_provider_error(
    error_info: ProviderErrorInfo,
    model: str,
    provider: str = "acp",
) -> None:
    """Raise BadRequestError or APIError based on status_code."""
    logger.error(
        f"Provider error: {error_info.message}",
        extra={
            "code": error_info.code,
            "param": error_info.param,
            "status_code": error_info.status_code,
        },
    )

    if error_info.status_code == 400:
        raise BadRequestError(
            message=error_info.message,
            model=model,
            llm_provider=provider,
        )
    else:
        raise InternalServerError(
            message=error_info.message,
            llm_provider=provider,
            model=model,
        )


def raise_stream_interrupted(
    message: str,
    model: str,
    provider: str = "acp",
) -> None:
    """Raise APIError(500) for mid-stream failures."""
    logger.error(f"Stream interrupted: {message}")
    raise APIError(
        status_code=500,
        message=message,
        model=model,
        llm_provider=provider,
    )
