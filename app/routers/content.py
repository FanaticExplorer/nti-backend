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
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.dependencies import get_current_user_optional, require_role
from app.models.contact_message import ContactMessage
from app.models.content import ContentPage, NewsArticle
from app.models.faq import FAQ
from app.models.program import Program
from app.models.user import User
from app.schemas.contact import ContactMessageCreate, ContactMessageOut
from app.schemas.content import (
    ContentPageCreate,
    ContentPageOut,
    ContentPageUpdate,
    NewsArticleCreate,
    NewsArticleOut,
    NewsArticleUpdate,
)
from app.schemas.faq import FAQCreate, FAQOut, FAQUpdate
from app.utils.sanitize import sanitize_html

from app.routers.auth import limiter
from app.utils.email import _send

router = APIRouter(prefix="/content", tags=["content"])


# ── Pages ──


@router.get("/pages")
async def list_pages(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a paginated list of content pages.

    Published-only for public; includes unpublished for editors/admins.
    """
    is_admin = current_user and current_user.role in ("content_editor", "nti_admin", "super_admin")
    query = select(ContentPage)
    count_query = select(func.count(ContentPage.id))
    if not is_admin:
        query = query.where(ContentPage.is_published)
        count_query = count_query.where(ContentPage.is_published)
    result = await db.execute(query.offset(skip).limit(limit))
    pages = result.scalars().all()
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
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
    result = await db.execute(
        select(ContentPage).where(
            ContentPage.slug == slug, ContentPage.is_published
        )
    )
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
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    is_admin = current_user and current_user.role in ("content_editor", "nti_admin", "super_admin")
    query = select(NewsArticle).order_by(NewsArticle.published_at.desc().nullslast())
    count_query = select(func.count(NewsArticle.id))
    if not is_admin:
        query = query.where(NewsArticle.is_published)
        count_query = count_query.where(NewsArticle.is_published)
    result = await db.execute(query.offset(skip).limit(limit))
    articles = result.scalars().all()
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
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
    if data.get("is_published") and not data.get("published_at"):
        data["published_at"] = datetime.now(timezone.utc)
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
    if update_data.get("is_published") and not article.published_at:
        update_data["published_at"] = datetime.now(timezone.utc)
    for key, value in update_data.items():
        setattr(article, key, value)
    await db.commit()
    await db.refresh(article)
    return article


# ── Contact ──


@router.post("/contact")
@limiter.limit("3/hour")
async def submit_contact_message(
    request: Request,
    body: ContactMessageCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    msg = ContactMessage(
        name=body.name,
        email=body.email,
        message=body.message,
    )
    db.add(msg)
    await db.commit()

    background_tasks.add_task(
        _send,
        "admin@nti.sk",
        f"New contact message from {body.name}",
        f"<p><b>From:</b> {body.name} ({body.email})</p><p>{body.message}</p>",
    )

    return {"detail": "Message sent"}


@router.get("/contact-messages")
async def list_contact_messages(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_read: bool | None = Query(None),
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(ContactMessage).order_by(ContactMessage.created_at.desc())
    if is_read is not None:
        query = query.where(ContactMessage.is_read == is_read)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(query.offset(skip).limit(limit))
    messages = result.scalars().all()

    return {
        "items": [ContactMessageOut.model_validate(m) for m in messages],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.patch("/contact-messages/{message_id}/read")
async def toggle_contact_message_read(
    message_id: uuid.UUID,
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContactMessage).where(ContactMessage.id == message_id)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )

    msg.is_read = not msg.is_read
    await db.commit()

    return ContactMessageOut.model_validate(msg)


# ── FAQ ──


@router.get("/faq")
async def list_faq(
    category: str | None = Query(None),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    is_admin = current_user and current_user.role in ("content_editor", "nti_admin", "super_admin")
    query = select(FAQ).order_by(FAQ.sort_order)
    if not is_admin:
        query = query.where(FAQ.is_published)
    if category:
        query = query.where(FAQ.category == category)

    result = await db.execute(query)
    items = result.scalars().all()
    return {"items": [FAQOut.model_validate(f) for f in items]}


@router.post("/faq", response_model=FAQOut, status_code=status.HTTP_201_CREATED)
async def create_faq(
    body: FAQCreate,
    current_user: User = Depends(require_role("content_editor", "nti_admin")),
    db: AsyncSession = Depends(get_db),
):
    faq = FAQ(**body.model_dump())
    db.add(faq)
    await db.commit()
    await db.refresh(faq)
    return faq


@router.patch("/faq/{faq_id}", response_model=FAQOut)
async def update_faq(
    faq_id: uuid.UUID,
    body: FAQUpdate,
    current_user: User = Depends(require_role("content_editor", "nti_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    faq = result.scalar_one_or_none()
    if not faq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found"
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(faq, key, value)
    await db.commit()
    await db.refresh(faq)
    return faq


@router.delete("/faq/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(
    faq_id: uuid.UUID,
    current_user: User = Depends(require_role("content_editor", "nti_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    faq = result.scalar_one_or_none()
    if not faq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found"
        )

    await db.delete(faq)
    await db.commit()


# ── Sitemap ──


@router.get("/sitemap.xml")
async def sitemap(db: AsyncSession = Depends(get_db)):
    base = settings.FRONTEND_URL.rstrip("/")
    pages = (await db.execute(
        select(ContentPage.slug).where(ContentPage.is_published)
    )).all()
    news = (await db.execute(
        select(NewsArticle.slug).where(NewsArticle.is_published)
    )).all()
    programs = (await db.execute(
        select(Program.id).where(Program.is_active)
    )).all()

    urls = []
    for slug in pages:
        urls.append(f"<url><loc>{base}/pages/{slug[0]}</loc></url>")
    for slug in news:
        urls.append(f"<url><loc>{base}/news/{slug[0]}</loc></url>")
    for pid in programs:
        urls.append(f"<url><loc>{base}/programs/{pid[0]}</loc></url>")

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(urls)
        + "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")
