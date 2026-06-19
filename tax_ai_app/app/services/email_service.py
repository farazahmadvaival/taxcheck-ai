import os

def send_email(email_to: str, subject: str, body: str) -> bool:
    """
    Sends an email using SendGrid or a stub in development.
    Returns: True if success, False otherwise.
    """
    print(f"==================================================")
    print(f"[EmailService] TRANSMITTING MESSAGE TO: {email_to}")
    print(f"Subject: {subject}")
    print(f"Body:\n{body}")
    print(f"==================================================")
    
    # SendGrid stub example (ready for expansion):
    # try:
    #     from sendgrid import SendGridAPIClient
    #     from sendgrid.helpers.mail import Mail
    #     message = Mail(
    #         from_email='noreply@taxcheck-ai.com',
    #         to_emails=email_to,
    #         subject=subject,
    #         plain_text_content=body
    #     )
    #     sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
    #     response = sg.send(message)
    #     return response.status_code in [200, 201, 202]
    # except Exception as err:
    #     print(f"[EmailService] Failed to send email via SendGrid: {err}")
    #     return False
    
    return True
