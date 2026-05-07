"""Structured logging via loguru.

Call `configure_logging()` exactly once at app startup. In development we
print human-readable coloured logs; in production we emit JSON so log
aggregators (Railway, CloudWatch, etc.) can parse them.
"""

from __future__ import annotations

import logging
import sys

from loguru import logger

from app.config import get_settings


class _InterceptHandler(logging.Handler):
    """Route stdlib logging (uvicorn, asyncpg, etc.) through loguru.

    Without this, uvicorn's access logs bypass loguru and we get two
    formats interleaved on stdout.
    """

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find the caller frame so file/line in log matches original call site.
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging() -> None:
    settings = get_settings()

    logger.remove()  # drop the default handler

    if settings.is_production:
        # JSON-serialised one-line records for log aggregators.
        logger.add(
            sys.stdout,
            level=settings.log_level,
            serialize=True,
            backtrace=False,
            diagnose=False,  # don't leak variable values in prod
        )
    else:
        logger.add(
            sys.stdout,
            level=settings.log_level,
            colorize=True,
            backtrace=True,
            diagnose=True,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
        )

    # Redirect stdlib logging (uvicorn, asyncpg) through loguru.
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access", "asyncpg"):
        logging.getLogger(noisy).handlers = [_InterceptHandler()]
        logging.getLogger(noisy).propagate = False
