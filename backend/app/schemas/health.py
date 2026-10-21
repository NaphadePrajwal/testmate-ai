from typing import Literal

from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    status: Literal["connected", "unavailable"]


class VectorDatabaseHealth(BaseModel):
    status: Literal["connected", "unavailable"]
    mode: str | None = None
    collection: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    database: DatabaseHealth
    vector_database: VectorDatabaseHealth | None = None
