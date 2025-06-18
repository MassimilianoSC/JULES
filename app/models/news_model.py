from typing import List, Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

class NewsIn(BaseModel):
    title: str
    body: str
    branch: Optional[List[str]] = Field(default_factory=list)
    employment_type: Optional[List[str]] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    show_on_home: Optional[bool] = False

class NewsOut(NewsIn):
    id: PyObjectId 