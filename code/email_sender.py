import os
from email.message import EmailMessage
import smtplib
from dotenv import load_dotenv

load_dotenv()

def build_email_message(
    sender,
    recipients,
    subject,
    body,
    html = None,
    cc = None,
    bcc = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = (
        ", ".join(recipients) if isinstance(recipients, (list, tuple)) else recipients
    )
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg.set_content(body)

    if html:
        msg.add_alternative(html, subtype="html")

    return msg


def send_email_gmail(
    sender,
    app_password,
    recipients,
    subject,
    body,
    html = None,
    cc = None,
    bcc = None,
    smtp_host = "smtp.gmail.com",
    smtp_port = 465,
    timeout = 10,
):
    if cc:
        recipients.extend(list(cc))
    if bcc:
        recipients.extend(list(bcc))

    msg = build_email_message(
        sender, recipients, subject, body, html=html, cc=cc, bcc=bcc
    )

    try:
        with smtplib.SMTP_SSL(host=smtp_host, port=smtp_port, timeout=timeout) as smtp:
            smtp.login(sender, app_password)
            smtp.send_message(msg, from_addr=sender, to_addrs=recipients)
        return True
    except smtplib.SMTPException:
        raise


if __name__ == "__main__":
    sender = "jsalazar6421@gmail.com"
    app_password = os.getenv("APP_PASSWORD")
    recipients = ["jsalaz59@asu.edu"]
    subject = "Test message from playground.notifier"
    body = "This is a test message. Replace credentials to actually send."
    html = "<body style='background: #123456'>Hello world!</body>"
    cc = ["jsalazar6421@gmail.com"]

    send_email_gmail(sender, app_password, recipients, subject, body, html, cc)
