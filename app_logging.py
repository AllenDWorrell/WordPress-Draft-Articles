"""Rotating local application logs with secret redaction."""
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


SECRET_PATTERNS=[
    re.compile(r'(?i)(authorization:\s*basic\s+)[^\s]+'),
    re.compile(r'(?i)((?:application[_ -]?password|password|secret)\s*[=:]\s*)[^\s,]+'),
]


def redact(message):
    text=str(message)
    for pattern in SECRET_PATTERNS:
        text=pattern.sub(r'\1[REDACTED]',text)
    return text


def configure(data_dir):
    log_dir=Path(data_dir)/'logs'
    log_dir.mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger('the-current')
    logger.setLevel(logging.INFO)
    logger.propagate=False
    if not logger.handlers:
        handler=RotatingFileHandler(log_dir/'the-current.log',maxBytes=2*1024*1024,
                                    backupCount=5,encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s %(message)s'
        ))
        logger.addHandler(handler)
    return logger
