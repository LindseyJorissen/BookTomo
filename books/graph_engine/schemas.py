from pydantic import BaseModel, Field
from typing import Optional


class BookNode(BaseModel):
    id: str
    title: str
    author: str
    rating: Optional[float] = Field(
        None,
        ge=1.0,
        le=5.0,
        description="User rating from Goodreads (1–5). Neutral if missing."
    )
