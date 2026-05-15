from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import SecretStr
from pydantic.networks import NameEmail

from app.config import settings

_mail_conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=SecretStr(settings.MAIL_PASSWORD),
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
)

_fm = FastMail(_mail_conf)


async def _send(to: str, subject: str, body: str) -> None:
    """Send an email. Falls back to console if no SMTP is configured."""
    if not settings.MAIL_USERNAME:
        print(f"[EMAIL] To: {to} | Subject: {subject}")
        return

    message = MessageSchema(
        subject=subject,
        recipients=[NameEmail("", to)],
        body=body,
        subtype=MessageType.html,
    )
    await _fm.send_message(message)


async def send_welcome_email(to: str) -> None:
    await _send(
        to,
        "Welcome to NTI — please verify your email",
        "<p>Welcome! Please verify your email by clicking the link in the verification email.</p>",
    )


async def send_email_verified(to: str) -> None:
    await _send(to, "Email verified", "<p>Your email has been verified.</p>")


async def send_application_submitted(to: str) -> None:
    await _send(
        to,
        "Your application has been received",
        "<p>Your application has been received and is being processed.</p>",
    )


async def send_status_change(to: str, new_status: str) -> None:
    subject_map = {
        "formally_verified": "Your application passed formal check",
        "under_evaluation": "Your application is being evaluated",
        "revision_requested": "Action required: revision requested",
        "approved": "Congratulations — application approved",
        "rejected": "Application decision",
        "onboarding": "Welcome to NTI — onboarding started",
    }
    subject = subject_map.get(new_status, f"Application status: {new_status}")
    await _send(
        to,
        subject,
        f"<p>Your application status is now: <strong>{new_status}</strong></p>",
    )


async def send_mentor_assigned(to: str) -> None:
    await _send(
        to,
        "Mentor assignment",
        "<p>A mentor has been assigned to your project.</p>",
    )


async def send_organization_approved(to: str) -> None:
    await _send(
        to,
        "Your organization has been approved",
        "<p>Your organization has been approved by NTI.</p>",
    )


async def send_password_reset(to: str, token: str) -> None:
    await _send(
        to,
        "Password reset request",
        f"<p>Click the link to reset your password: /reset-password?token={token}</p>",
    )
