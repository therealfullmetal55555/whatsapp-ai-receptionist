"""
Dialog agent with function calling - GPT-6 Sol
Handles booking intent, checks availability, confirms before write
"""
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
import pytz

from .config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL, USE_MOCK_LLM, BUSINESS_NAME, TIMEZONE, CLIENT_TIMEZONE
from .calendar_tools import CALENDAR_FUNCTIONS, handle_function_call

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""You are an AI receptionist for {BUSINESS_NAME}, a wellness studio in Tallinn, Estonia.

Your role:
- Receive WhatsApp messages from clients wanting to book, reschedule, or cancel appointments
- Understand intent: book / reschedule / cancel / question
- Check availability via function calling
- Propose slots
- Confirm before booking (confirm-before-write) - never book without explicit yes from user
- Handle timezones explicitly: calendar is in {TIMEZONE}, log client timezone if mentioned

Business hours: 09:00-18:00, slot duration 60 minutes, timezone {TIMEZONE}

Rules:
- Be friendly, concise, helpful, in English (or client's language if they write in Estonian/Russian)
- Always mention timezone when proposing slots: e.g., "10:00-11:00 Europe/Tallinn"
- Before booking, summarize: date, time, timezone, service, and ask for confirmation
- Only after user says yes/confirms, call book_slot function
- If user wants to cancel, ask for event ID or date/time to find booking
- If out of scope (e.g., asking about politics), politely say you can only help with bookings
- Log client timezone and calendar timezone in function calls

Example flow:
User: Hi, I want to book wellness appointment tomorrow
Assistant: Sure! Let me check availability for tomorrow (2024-09-30) in Europe/Tallinn timezone. [calls check_availability]
Assistant: I found slots: 09:00-10:00, 11:00-12:00, 15:00-16:00 Europe/Tallinn. Which works for you?
User: 11:00 works
Assistant: Great! To confirm: wellness appointment on 2024-09-30 11:00-12:00 Europe/Tallinn for [name]. Is that correct? Please confirm with yes.
User: Yes
Assistant: [calls book_slot with start_iso=2024-09-30T11:00:00+03:00, etc.] Booking confirmed!

Current date: {datetime.now().isoformat()} in timezone {TIMEZONE}
"""

class ConversationState:
    def __init__(self, user_id: str, user_name: str = "", client_timezone: str = CLIENT_TIMEZONE):
        self.user_id = user_id
        self.user_name = user_name
        self.client_timezone = client_timezone
        self.history: List[Dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.pending_booking: Optional[Dict] = None  # Stores slot waiting for confirmation
    
    def add_user_message(self, message: str):
        self.history.append({"role": "user", "content": message})
    
    def add_assistant_message(self, message: str):
        self.history.append({"role": "assistant", "content": message})
    
    def add_function_result(self, function_name: str, result: dict):
        self.history.append({
            "role": "tool",
            "tool_call_id": f"call_{function_name}",
            "name": function_name,
            "content": json.dumps(result)
        })

# In-memory conversation store (for demo, use Redis in prod)
conversations: Dict[str, ConversationState] = {}

def get_conversation(user_id: str, user_name: str = "", client_timezone: str = CLIENT_TIMEZONE) -> ConversationState:
    if user_id not in conversations:
        conversations[user_id] = ConversationState(user_id, user_name, client_timezone)
    # Update timezone if provided
    if client_timezone:
        conversations[user_id].client_timezone = client_timezone
    return conversations[user_id]

def mock_agent_response(user_id: str, message: str, user_name: str = "") -> Dict:
    """
    Mock agent that simulates function calling without real LLM
    For portfolio demo without API key
    """
    import re
    conv = get_conversation(user_id, user_name)
    conv.add_user_message(message)
    
    msg_lower = message.lower()
    
    # Check for confirmation
    if conv.pending_booking and any(word in msg_lower for word in ["yes", "confirm", "да", "jah", "ok", "book it"]):
        # User confirmed pending booking
        booking = conv.pending_booking
        result = handle_function_call("book_slot", {
            **booking,
            "client_timezone": conv.client_timezone
        })
        conv.pending_booking = None
        if result.get("success"):
            response = f"✅ Booking confirmed! {booking['summary']} on {booking['start_iso']} Europe/Tallinn (calendar TZ: {TIMEZONE}, your TZ: {conv.client_timezone}). Event ID: {result['event']['id']}. See you soon at {BUSINESS_NAME}!"
        else:
            response = f"❌ Failed to book: {result.get('error')}. Please try another slot."
        conv.add_assistant_message(response)
        return {"response": response, "function_called": "book_slot", "result": result, "mock": True}
    
    # Check for booking intent
    if any(word in msg_lower for word in ["book", "appointment", "reserve", "записаться", "broneerida", "schedule"]):
        # Extract date - simple: tomorrow, today, or specific date
        from datetime import timedelta
        import re
        
        target_date = None
        if "tomorrow" in msg_lower or "завтра" in msg_lower or "homme" in msg_lower:
            target_date = (datetime.now(pytz.timezone(TIMEZONE)) + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "today" in msg_lower or "сегодня" in msg_lower or "täna" in msg_lower:
            target_date = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
        else:
            # Try to find YYYY-MM-DD or DD.MM.YYYY
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', message)
            if date_match:
                target_date = date_match.group(1)
            else:
                date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', message)
                if date_match:
                    d,m,y = date_match.group(1).split('.')
                    target_date = f"{y}-{m}-{d}"
        
        if not target_date:
            target_date = (datetime.now(pytz.timezone(TIMEZONE)) + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Check availability
        avail_result = handle_function_call("check_availability", {
            "date": target_date,
            "duration_minutes": 60,
            "client_timezone": conv.client_timezone
        })
        
        slots = avail_result.get("available_slots", [])
        if not slots:
            response = f"Sorry, no available slots for {target_date} in {TIMEZONE}. Would you like to try another date?"
        else:
            # Propose first 3 slots
            slot_texts = [f"{s['start_time']}-{s['end_time']} {TIMEZONE}" for s in slots[:3]]
            response = f"I found {len(slots)} available slots for {target_date} ({TIMEZONE}, your TZ: {conv.client_timezone}): {', '.join(slot_texts)}. Which one works for you?"
            # Store first slot as pending for demo? Actually wait for user choice
            # For simplicity, store all slots in conversation state for next turn
            conv.pending_slots = slots
        
        conv.add_assistant_message(response)
        return {"response": response, "function_called": "check_availability", "result": avail_result, "mock": True}
    
    # Check if user selected a time like "11:00"
    time_match = re.search(r'(\d{1,2}:\d{2})', message)
    if time_match and hasattr(conv, 'pending_slots'):
        selected_time = time_match.group(1)
        # Find slot matching that time
        for slot in conv.pending_slots:
            if slot["start_time"] == selected_time or selected_time in slot["start_time"]:
                # Prepare pending booking for confirmation
                conv.pending_booking = {
                    "start_iso": slot["start_iso"],
                    "end_iso": slot["end_iso"],
                    "summary": f"Wellness appointment - {conv.user_name or user_id}",
                    "description": f"Booking via WhatsApp from {conv.user_name}",
                    "attendee_name": conv.user_name or user_id,
                    "attendee_email": "",
                }
                response = f"Great! To confirm: wellness appointment on {slot['date']} {slot['start_time']}-{slot['end_time']} {TIMEZONE} (calendar TZ: {TIMEZONE}, your TZ: {conv.client_timezone}) for {conv.user_name or 'you'}. Is that correct? Please confirm with yes."
                conv.add_assistant_message(response)
                return {"response": response, "function_called": None, "result": {"pending_booking": conv.pending_booking}, "mock": True}
    
    # Default response
    response = f"Hello! I'm AI receptionist for {BUSINESS_NAME}. I can help you book, reschedule, or cancel appointments. Our hours are 09:00-18:00 {TIMEZONE}. What would you like to do?"
    conv.add_assistant_message(response)
    return {"response": response, "function_called": None, "result": {}, "mock": True}

def llm_agent_response(user_id: str, message: str, user_name: str = "", client_timezone: str = CLIENT_TIMEZONE) -> Dict:
    """
    Real LLM agent with function calling (GPT-6 Sol / OpenAI compatible)
    """
    if USE_MOCK_LLM:
        return mock_agent_response(user_id, message, user_name)
    
    try:
        from openai import OpenAI
        conv = get_conversation(user_id, user_name, client_timezone)
        conv.add_user_message(message)
        
        client_kwargs = {}
        if OPENAI_BASE_URL:
            client_kwargs["base_url"] = OPENAI_BASE_URL
        client_kwargs["api_key"] = OPENAI_API_KEY
        client = OpenAI(**client_kwargs)
        
        # First call - with functions
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=conv.history,
            tools=CALENDAR_FUNCTIONS,
            tool_choice="auto",
            temperature=0.3,
        )
        
        assistant_message = response.choices[0].message
        
        # Check if function call
        if assistant_message.tool_calls:
            # Add assistant message with tool calls to history
            conv.history.append({
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    } for tc in assistant_message.tool_calls
                ]
            })
            
            # Execute each function call
            function_results = []
            for tool_call in assistant_message.tool_calls:
                func_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                    # Ensure client_timezone logged
                    if "client_timezone" not in args:
                        args["client_timezone"] = conv.client_timezone
                    result = handle_function_call(func_name, args)
                    function_results.append((tool_call.id, func_name, result))
                    
                    # Add tool result to history
                    conv.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": json.dumps(result)
                    })
                except Exception as e:
                    logger.error(f"Function call {func_name} failed: {e}")
                    error_result = {"success": False, "error": str(e)}
                    conv.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": json.dumps(error_result)
                    })
                    function_results.append((tool_call.id, func_name, error_result))
            
            # Second call - get final response after function results
            second_response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=conv.history,
                temperature=0.3,
            )
            
            final_message = second_response.choices[0].message.content
            conv.add_assistant_message(final_message)
            
            return {
                "response": final_message,
                "function_called": function_results[0][1] if function_results else None,
                "result": function_results[0][2] if function_results else {},
                "mock": False
            }
        else:
            # No function call, just text response
            final_message = assistant_message.content
            conv.add_assistant_message(final_message)
            return {
                "response": final_message,
                "function_called": None,
                "result": {},
                "mock": False
            }
    
    except Exception as e:
        logger.error(f"LLM agent failed, fallback to mock: {e}")
        return mock_agent_response(user_id, message, user_name)

def handle_message(user_id: str, message: str, user_name: str = "", client_timezone: str = CLIENT_TIMEZONE) -> Dict:
    """
    Main entry point - handles incoming WhatsApp message
    """
    return llm_agent_response(user_id, message, user_name, client_timezone)

if __name__ == "__main__":
    # Test conversation
    print("=== Test Conversation (Mock) ===")
    user_id = "test_user_123"
    
    messages = [
        "Hi, I want to book wellness appointment tomorrow",
        "11:00 works",
        "Yes"
    ]
    
    for msg in messages:
        print(f"\nUser: {msg}")
        result = handle_message(user_id, msg, user_name="Anna Schmidt", client_timezone="Europe/Tallinn")
        print(f"Bot: {result['response']}")
        if result.get("function_called"):
            print(f"  Function: {result['function_called']}")
