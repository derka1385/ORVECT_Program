import logging
import structlog
from app.core.config import settings

def configure_logging():
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    # Les URL vPIC contiennent le VIN dans leur chemin : ne jamais laisser
    # le journal HTTP générique les sérialiser en niveau INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    structlog.configure(processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()])

logger = structlog.get_logger()
