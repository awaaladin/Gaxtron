import asyncio
import logging

from app.core.logging_config import setup_logging
from app.db.base import Base
from app.db.session import engine
from app.workers.listener import BlockchainListener

setup_logging()
logger = logging.getLogger(__name__)


def init_db():
    import app.db.models  # noqa: F401
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    listener = BlockchainListener()
    asyncio.run(listener.run())
