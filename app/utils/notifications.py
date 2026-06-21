import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def create_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    body: str,
    action_type: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
):
    notif = Notification(
        user_id=user_id,
        title=title,
        body=body,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(notif)
    await db.commit()
