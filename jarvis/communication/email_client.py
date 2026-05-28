import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from typing import List, Dict, Any

class EmailClient:
    def __init__(self, smtp_server: str = "smtp.gmail.com", smtp_port: int = 587,
                 imap_server: str = "imap.gmail.com", imap_port: int = 993):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.logger = logging.getLogger("Jarvis.EmailClient")

    def send_email(self, username: str, password_or_token: str, to_addr: str, subject: str, body: str):
        """Sends an email via SMTP."""
        self.logger.info(f"Sending email to {to_addr} (Subject: {subject})...")
        try:
            msg = MIMEMultipart()
            msg['From'] = username
            msg['To'] = to_addr
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(username, password_or_token)
            server.sendmail(username, to_addr, msg.as_string())
            server.quit()
            self.logger.info("Email sent successfully.")
            return "Email sent successfully."
        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")
            raise RuntimeError(f"Email delivery failed: {e}")

    def fetch_recent_emails(self, username: str, password_or_token: str, count: int = 5) -> List[Dict[str, Any]]:
        """Fetches recent emails via IMAP."""
        self.logger.info("Fetching recent emails from inbox...")
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(username, password_or_token)
            mail.select("inbox")

            status, data = mail.search(None, "ALL")
            mail_ids = data[0].split()
            
            recent_ids = mail_ids[-count:]
            recent_ids.reverse()

            emails_list = []
            for m_id in recent_ids:
                status, msg_data = mail.fetch(m_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = email.header.decode_header(msg["Subject"])[0][0]
                        if isinstance(subject, bytes):
                            subject = subject.decode()
                        from_ = msg.get("From")
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode()
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode()

                        emails_list.append({
                            "id": m_id.decode(),
                            "from": from_,
                            "subject": subject,
                            "body": body.strip()[:200]  # Snippet
                        })

            mail.close()
            mail.logout()
            return emails_list
        except Exception as e:
            self.logger.error(f"Failed to fetch emails: {e}")
            raise RuntimeError(f"Email fetch failed: {e}")
