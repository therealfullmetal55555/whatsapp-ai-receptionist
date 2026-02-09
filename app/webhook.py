"""
FastAPI webhook for Twilio WhatsApp
Receives incoming messages via Twilio webhook
"""
import logging
from fastapi import FastAPI, Request, Form
from fastapi.responses import PlainTextResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from .config import BASE_DIR, USE_MOCK_TWILIO, TWILIO_WHATSAPP_NUMBER, BUSINESS_NAME
from .agent import handle_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=f"{BUSINESS_NAME} - WhatsApp AI Receptionist", version="1.0.0")

templates_dir = BASE_DIR / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "whatsapp-receptionist",
        "twilio_mock": USE_MOCK_TWILIO,
        "whatsapp_number": TWILIO_WHATSAPP_NUMBER,
        "business": BUSINESS_NAME
    }

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    ProfileName: str = Form(None),
    MessageSid: str = Form(None),
    WaId: str = Form(None)
):
    """
    Twilio WhatsApp webhook - receives incoming WhatsApp messages
    Twilio sends form-encoded data: From, Body, ProfileName, etc.
    """
    logger.info(f"Incoming WhatsApp from {From} ({ProfileName}): {Body[:100]}...")
    
    # Extract user info
    user_id = WaId or From  # WaId is WhatsApp ID without prefix
    user_name = ProfileName or From
    
    # Handle message via agent
    try:
        result = handle_message(
            user_id=user_id,
            message=Body,
            user_name=user_name,
            client_timezone="Europe/Tallinn"  # Could be extracted from user profile if available
        )
        
        response_text = result["response"]
        
        # In real Twilio, you return TwiML or use Twilio client to send message
        # For simplicity, we return plain text that Twilio will send as reply
        # In production, you'd use Twilio client:
        # from twilio.rest import Client
        # client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, to=From, body=response_text)
        
        logger.info(f"Reply to {From}: {response_text[:100]}...")
        
        # Return TwiML for Twilio to send as WhatsApp reply
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response_text}</Message>
</Response>"""
        
        return PlainTextResponse(content=twiml, media_type="application/xml")
    
    except Exception as e:
        logger.exception(f"Webhook handling failed: {e}")
        error_twiML = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>Sorry, I encountered an error. Please try again or contact support.</Message>
</Response>"""
        return PlainTextResponse(content=error_twiML, media_type="application/xml")

@app.post("/webhook/whatsapp/mock")
async def whatsapp_mock_webhook(request: Request):
    """
    Mock webhook for testing without Twilio - accepts JSON
    {
        "From": "whatsapp:+3725xxxxxxx",
        "Body": "Hi, I want to book appointment tomorrow",
        "ProfileName": "Anna"
    }
    """
    try:
        data = await request.json()
        From = data.get("From", "whatsapp:+37250000000")
        Body = data.get("Body", "")
        ProfileName = data.get("ProfileName", "Test User")
        WaId = data.get("WaId", From.replace("whatsapp:", ""))
        
        result = handle_message(
            user_id=WaId,
            message=Body,
            user_name=ProfileName,
            client_timezone=data.get("client_timezone", "Europe/Tallinn")
        )
        
        return {
            "status": "success",
            "from": From,
            "body": Body,
            "response": result["response"],
            "function_called": result.get("function_called"),
            "mock": result.get("mock", False)
        }
    
    except Exception as e:
        logger.exception(f"Mock webhook failed: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/demo/transcripts", response_class=HTMLResponse)
async def demo_transcripts(request: Request):
    transcripts_path = BASE_DIR / "demo" / "conversation-transcripts.md"
    if transcripts_path.exists():
        content = transcripts_path.read_text(encoding='utf-8')
        # Simple render
        html = f"<html><body><pre>{content}</pre></body></html>"
        return HTMLResponse(content=html)
    else:
        return HTMLResponse(content="<html><body>No transcripts yet. Run tests or real Twilio sandbox test.</body></html>")

if __name__ == "__main__":
    import uvicorn
    from .config import APP_HOST, APP_PORT
    uvicorn.run("app.webhook:app", host=APP_HOST, port=APP_PORT, reload=True)
