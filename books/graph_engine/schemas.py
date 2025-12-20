from pydantic import BaseModel
from typing import List

class BookNode(BaseModel):
  id: str
  title: str
  authors: List[str]
  genres: List[str]
