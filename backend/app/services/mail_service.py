import smtplib
from email.message import EmailMessage

from app.core.config import Settings


def send_password_reset_email(*, settings: Settings, to_email: str, otp: str) -> None:
    if not settings.smtp_is_configured:
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = "MedDataHub password reset code"
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message.set_content(
        f"Your MedDataHub password reset code is {otp}.\n\n"
        f"This code expires in {settings.otp_ttl_seconds // 60} minutes. "
        "If you did not request a password reset, you can ignore this email.\n"
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password)
        client.send_message(message)
