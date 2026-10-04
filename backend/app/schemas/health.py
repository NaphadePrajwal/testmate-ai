from typing import Literal

from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    status: Literal["connected", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    database: DatabaseHealth
