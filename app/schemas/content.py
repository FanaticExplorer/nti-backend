from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ContentPageCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    body: str
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_image_url: Optional[str] = None
    is_published: bool = False


class ContentPageUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_image_url: Optional[str] = None
    is_published: Optional[bool] = None


class ContentPageOut(BaseModel):
    id: UUID
    slug: str
    title: str
    body: str
    meta_title: Optional[str]
    meta_description: Optional[str]
    og_image_url: Optional[str]
    is_published: bool
    created_by: UUID
    updated_at: datetime

    model_config = {"from_attributes": True}


class NewsArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100)
    body: str
    published_at: Optional[datetime] = None
    is_published: bool = False


class NewsArticleUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    published_at: Optional[datetime] = None
    is_published: Optional[bool] = None


class NewsArticleOut(BaseModel):
    id: UUID
    title: str
    slug: str
    body: str
    published_at: Optional[datetime]
    is_published: bool
    author_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
