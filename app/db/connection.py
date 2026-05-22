import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config.env_loader import load_dotenv

load_dotenv()

try:
    from psycopg_pool import ConnectionPool
except ModuleNotFoundError:
    ConnectionPool = None


_pool: Any | None = None


def require_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("请先设置环境变量 DATABASE_URL")
    return database_url


def get_pool():
    global _pool
    if ConnectionPool is None:
        return None
    if _pool is None:
        _pool = ConnectionPool(
            require_database_url(),
            min_size=int(os.getenv("DATABASE_POOL_MIN_SIZE", "1")),
            max_size=int(os.getenv("DATABASE_POOL_MAX_SIZE", "10")),
            kwargs={"row_factory": dict_row},
        )
    return _pool


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    pool = get_pool()
    if pool is not None:
        with pool.connection() as conn:
            yield conn
        return

    with psycopg.connect(require_database_url(), row_factory=dict_row) as conn:
        yield conn


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
