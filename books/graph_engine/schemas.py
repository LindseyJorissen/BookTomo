from pydantic import BaseModel
from typing import List

class BookNode(BaseModel):
  id: str
  title: str
  authors: List[str]
  genres: List[str]
  rating: Optional[float] = Field(None,ge1.0, le=5.0)
