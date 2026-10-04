from typing import Annotated

from fastapi import Query
from pydantic import BaseModel


class Pagination(BaseModel):
    limit: int = 20
    offset: int = 0


def pagination_params(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)
