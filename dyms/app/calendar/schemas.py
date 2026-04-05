from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DragCommit(BaseModel):
    appointment_id: int
    dock_id: int
    start: datetime
    end: datetime
