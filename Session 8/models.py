from pydantic import BaseModel
from typing import List

class F1Standings(BaseModel):
    team: str
    points: int
