"""
Content router — CMS pages and news articles.

Manages two kinds of published content:

**Pages** (``/pages``)
    Static CMS pages identified by a unique slug. Publicly readable;
    creation and updates require ``content_editor`` or ``nti_admin`` role.

**News** (``/news``)
    Blog-style news articles with publication dates. Publicly readable;
    creation and updates require ``content_editor`` or ``nti_admin`` role.

Both resources support slug-based lookup for public readers and ID-based
lookup for editors.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.content import ContentPage, NewsArticle
from app.models.user import User
from app.schemas.content import (
    ContentPageCreate,
    ContentPageOut,
    ContentPageUpdate,
    NewsArticleCreate,
    NewsArticleOut,
    NewsArticleUpdate,
)
from app.utils.sanitize import sanitize_html

router = APIRouter(prefix="/content", tags=["content"])


# ── Pages ──


@router.get("/pages")
async def list_pages(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a paginated list of published content pages.

    Only pages where ``is_published == True`` are returned.

    **Access**: public
    """
    result = await db.execute(
        select(ContentPage).where(ContentPage.is_published).offset(skip).limit(limit)
    )
    pages = result.scalars().all()
    total_result = await db.execute(select(ContentPage).where(ContentPage.is_published))
    total = len(total_result.scalars().all())
    return {
        "items": [ContentPageOut.model_validate(p) for p in pages],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/pages/{slug}", response_model=ContentPageOut)
async def get_page(slug: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a single content page by its slug.

    Returns 404 if no page with the given slug exists.

    **Access**: public
    """
    result = await db.execute(select(ContentPage).where(ContentPage.slug == slug))
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found"
        )
    return page


@router.post(
    "/pages", response_model=ContentPageOut, status_code=status.HTTP_201_CREATED
)
async def create_page(
    body: ContentPageCreate,
    current_user: User = Depends(require_role("content_editor", "nti_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new content page.

    Returns 409 if the slug is already taken. The ``created_by`` field
    is set to the authenticated user's ID.

    **Access**: ``content_editor``, ``nti_admin``
    """
    existing = await db.execute(
        select(ContentPage).where(ContentPage.slug == body.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Slug already exists"
        )

    data = body.model_dump()
    data["body"] = sanitize_html(data["body"])
    page = ContentPage(created_by=current_user.id, **data)
    db.add(page)
    await db.commit()
    await db.refresh(page)
    return page


@router.put("/pages/{page_id}", response_model=ContentPageOut)
async def update_page(
    page_id: uuid.UUID,
    body: ContentPageUpdate,
    current_user: User = Depends(require_role("content_editor", "nti_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing content page by ID.

    Only fields present in the request body are updated (partial update).
    Returns 404 if the page does not exist.

    **Access**: ``content_editor``, ``nti_admin``
    """
    result = await db.execute(select(ContentPage).where(ContentPage.id == page_id))
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found"
        )

    update_data = body.model_dump(exclude_unset=True)
    if "body" in update_data:
        update_data["body"] = sanitize_html(update_data["body"])
    for key, value in update_data.items():
        setattr(page, key, value)
    await db.commit()
    await db.refresh(page)
    return page


# ── News ──


@router.get("/news")
async def list_news(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a paginated list of published news articles.

    Only articles where ``is_published == True`` are returned, ordered
    by ``published_at`` descending (newest first). Articles with a null
    ``published_at`` are placed at the end.

    **Access**: public
    """
    result = await db.execute(
        select(NewsArticle)
        .where(NewsArticle.is_published)
        .order_by(NewsArticle.published_at.desc().nullslast())
        .offset(skip)
        .limit(limit)
    )
    articles = result.scalars().all()
    total_result = await db.execute(select(NewsArticle).where(NewsArticle.is_published))
    total = len(total_result.scalars().all())
    return {
        "items": [NewsArticleOut.model_validate(a) for a in articles],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/news/{slug}", response_model=NewsArticleOut)
async def get_news_article(slug: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a single news article by its slug.

    Returns 404 if no article with the given slug exists.

    **Access**: public
    """
    result = await db.execute(select(NewsArticle).where(NewsArticle.slug == slug))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        )
    return article


@router.post(
    "/news", response_model=NewsArticleOut, status_code=status.HTTP_201_CREATED
)
async def create_news_article(
    body: NewsArticleCreate,
    current_user: User = Depends(require_role("content_editor", "nti_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new news article.

    Returns 409 if the slug is already taken. The ``author_id`` field
    is set to the authenticated user's ID.

    **Access**: ``content_editor``, ``nti_admin``
    """
    existing = await db.execute(
        select(NewsArticle).where(NewsArticle.slug == body.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Slug already exists"
        )

    data = body.model_dump()
    data["body"] = sanitize_html(data["body"])
    article = NewsArticle(
        author_id=current_user.id,
        **data,
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


@router.put("/news/{article_id}", response_model=NewsArticleOut)
async def update_news_article(
    article_id: uuid.UUID,
    body: NewsArticleUpdate,
    current_user: User = Depends(require_role("content_editor", "nti_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing news article by ID.

    Only fields present in the request body are updated (partial update).
    Returns 404 if the article does not exist.

    **Access**: ``content_editor``, ``nti_admin``
    """
    result = await db.execute(select(NewsArticle).where(NewsArticle.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        )

    update_data = body.model_dump(exclude_unset=True)
    if "body" in update_data:
        update_data["body"] = sanitize_html(update_data["body"])
    for key, value in update_data.items():
        setattr(article, key, value)
    await db.commit()
    await db.refresh(article)
    return article
