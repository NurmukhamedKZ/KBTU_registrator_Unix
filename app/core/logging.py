import logging
import os


def setup_backend_logging() -> logging.Logger:
    """Configure human-readable backend logs and mute noisy polling access logs."""
    logger = logging.getLogger("uni_bot")
    if logger.handlers:
        return logger

    level_name = os.getenv("APP_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        "%(levelname)-8s | %(asctime)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_file = os.getenv("APP_LOG_FILE", "backend.log").strip()
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False

    # Hide noisy request spam from frequent polling endpoints in terminal output.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return logger
