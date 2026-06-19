import json
import urllib.request
import urllib.error
from app.config import settings

class GoogleAntigravityClient:
    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def generate_content(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("API Key is not configured.")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }]
        }
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode("utf-8"), 
            headers=headers, 
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            
        return res_data["candidates"][0]["content"]["parts"][0]["text"].strip()

# Initialize Google Antigravity client wrapper
client = GoogleAntigravityClient(api_key=settings.GEMINI_API_KEY)

def generate_email_draft(client_name: str, approved_items: list[dict]) -> tuple[str, str]:
    """
    Calls the Google Antigravity client wrapper to generate a polished email requesting missing documents.
    If the API key is not set or the API call fails, falls back to a clean, templated layout.
    
    Returns: (subject, body)
    """
    # Format the approved items into a readable string
    items_list_str = ""
    for item in approved_items:
        items_list_str += f"- {item['title']}: {item['description']}"
        if item.get('recommended_document'):
            items_list_str += f" (Recommended: {item['recommended_document']})"
        items_list_str += "\n"
        
    prompt = (
        f"You are a professional CPA tax preparation assistant. Synthesize a polished, friendly, and professional "
        f"document request email to the client '{client_name}' based on the following outstanding missing documents or anomalies:\n\n"
        f"{items_list_str}\n"
        f"Instructions:\n"
        f"1. Keep the tone friendly, helpful, and professional.\n"
        f"2. Explain why each document or explanation is needed in simple terms.\n"
        f"3. Provide two distinct outputs separated by a delimiter line '===DELIMITER===':\n"
        f"   - The first line must be the Subject of the email.\n"
        f"   - The second part must be the Body of the email.\n"
        f"Example format:\n"
        f"Subject: Action Required: Missing Documents for Your 2025 Tax Return\n"
        f"===DELIMITER===\n"
        f"Dear {client_name},\n\n..."
    )
    
    if client.api_key:
        try:
            text_out = client.generate_content(prompt)
            
            # Parse subject and body
            if "===DELIMITER===" in text_out:
                parts = text_out.split("===DELIMITER===")
                subject = parts[0].replace("Subject:", "").strip()
                body = parts[1].strip()
                return subject, body
            else:
                # Fallback parse if delimiter missing
                lines = text_out.split("\n")
                subject = "Action Required: Outstanding Tax Documents for Your Tax Return"
                for line in lines:
                    if line.lower().startswith("subject:"):
                        subject = line[8:].strip()
                        break
                body = text_out
                return subject, body
                
        except Exception as e:
            print(f"[LLM] Client wrapper failed to generate content, using template fallback. Error: {e}")
            
    # --- Template Fallback ---
    subject = f"Action Required: Outstanding Documents for Your Tax Return"
    
    body = (
        f"Dear {client_name},\n\n"
        f"We are currently preparing your tax return and have identified a few outstanding items "
        f"or anomalies that require your attention. To help us complete your return accurately "
        f"and efficiently, please provide the following documents or explanations:\n\n"
    )
    
    for item in approved_items:
        body += f"• {item['title']}\n"
        body += f"  Detail: {item['description']}\n"
        if item.get('recommended_document'):
            body += f"  Requested Document: {item['recommended_document']}\n"
        body += "\n"
        
    body += (
        f"Please reply to this email with the requested information or upload the files "
        f"directly through your client portal.\n\n"
        f"If you have any questions or need assistance, feel free to contact us.\n\n"
        f"Best regards,\n"
        f"Your Tax Preparation Team"
    )
    
    return subject, body
