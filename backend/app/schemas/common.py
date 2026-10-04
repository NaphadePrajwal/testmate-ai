from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    """Strict base model for public API contracts."""

    model_config = ConfigDict(extra="forbid")


class PageMeta(APIModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
