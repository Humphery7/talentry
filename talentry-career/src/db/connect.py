from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import Depends, Request
from psycopg_pool import ConnectionPool

from config.settings import get_database_url


def create_pool() -> ConnectionPool:
    return ConnectionPool(
        conninfo=get_database_url(),
        min_size=1,
        max_size=5,
    )


def get_connection(request: Request) -> Iterator[psycopg.Connection]:
    with request.app.state.pool.connection() as conn:
        yield conn


ConnectionDep = Annotated[
    psycopg.Connection,
    Depends(get_connection, scope="function"),
]
