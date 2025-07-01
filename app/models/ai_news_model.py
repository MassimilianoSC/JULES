from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from enum import Enum

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")

class AINewsBase(BaseModel):
    title: str
    description: str
    section: str
    branch: str
    employment_type: str = "*"
    category: Literal["generic", "business", "technical", "other"] = Field(
        default="generic",
        description="Categoria della news: generic, business, technical, other"
    )
    tags: List[str] = Field(default_factory=list)
    content: Dict[str, str] = Field(...) # {type: "file|url", filename?: str, external_url?: str}
    content_type: Optional[str] = None
    show_on_home: bool = False
    metadata: Dict = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Nuova Feature AI",
                "description": "Descrizione della feature",
                "section": "novità",
                "branch": "HQE",
                "employment_type": "*",
                "category": "technical",
                "tags": ["ai", "feature"],
                "content": {"type": "file", "filename": "documento.pdf"},
                "show_on_home": False
            }
        }

class AINewsDB(AINewsBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    author_id: PyObjectId
    uploaded_at: datetime
    stats: Dict[str, int] = Field(
        default_factory=lambda: {
            "views": 0,
            "likes": 0,
            "comments": 0,
            "replies": 0,
            "total_interactions": 0
        }
    )

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class CommentBase(BaseModel):
    content: str
    parent_id: Optional[PyObjectId] = None
    metadata: Dict = Field(default_factory=dict)
    mentions: Optional[list[str]] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "content": "Ottimo articolo!",
                "parent_id": None,
                "metadata": {},
                "mentions": []
            }
        }

class CommentDB(CommentBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    news_id: PyObjectId
    author_id: PyObjectId
    created_at: datetime
    updated_at: Optional[datetime] = None
    likes: int = 0
    replies_count: int = 0

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class ViewActionType(str, Enum):
    PREVIEW = "preview"
    DOWNLOAD = "download"
    VIEW = "view"

class ViewIn(BaseModel):
    action_type: ViewActionType = Field(default=ViewActionType.VIEW)

class ViewDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    news_id: PyObjectId
    last_view: datetime
    action: ViewActionType

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str} 