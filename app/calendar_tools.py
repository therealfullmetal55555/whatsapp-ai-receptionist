"""
Calendar tools - Google Calendar API wrapper + mock for demo
Source of truth for slots

Handles timezones explicitly - common bug cause for booking
"""
import logging
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional
import pytz

from .config import GOOGLE_CALENDAR_ID, GOOGLE_CREDENTIALS_PATH, USE_MOCK_CALENDAR, TIMEZONE, BUSINESS_HOURS_START, BUSINESS_HOURS_END, SLOT_DURATION

logger = logging.getLogger(__name__)

# Mock calendar storage
class MockCalendar:
    def __init__(self, timezone_str: str = TIMEZONE):
        self.timezone = pytz.timezone(timezone_str)
        self.events: List[Dict] = []
        self.next_id = 1
        # Pre-populate with some busy slots for demo
        now = datetime.now(self.timezone)
        # Add some busy slots tomorrow
        tomorrow = now + timedelta(days=1)
        for hour in [10, 14, 16]:
            start = tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=SLOT_DURATION)
            self.events.append({
                "id": f"mock_{self.next_id}",
                "summary": "Busy - Existing Appointment",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "status": "confirmed",
                "description": "Pre-existing booking for demo"
            })
            self.next_id += 1
    
    def _parse_time(self, time_str: str) -> time:
        h, m = map(int, time_str.split(':'))
        return time(h, m)
    
    def get_available_slots(self, date_str: str, duration_minutes: int = SLOT_DURATION) -> List[Dict]:
        """
        Get available slots for a given date (YYYY-MM-DD)
        Returns list of {start, end, start_iso, end_iso} in calendar timezone
        """
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            # Try to parse natural language? For mock, return next 3 days
            target_date = (datetime.now(self.timezone) + timedelta(days=1)).date()
        
        start_time = self._parse_time(BUSINESS_HOURS_START)
        end_time = self._parse_time(BUSINESS_HOURS_END)
        
        # Generate all possible slots
        all_slots = []
        current = datetime.combine(target_date, start_time)
        current = self.timezone.localize(current)
        end_of_day = datetime.combine(target_date, end_time)
        end_of_day = self.timezone.localize(end_of_day)
        
        while current + timedelta(minutes=duration_minutes) <= end_of_day:
            slot_end = current + timedelta(minutes=duration_minutes)
            all_slots.append({
                "start": current,
                "end": slot_end,
                "start_iso": current.isoformat(),
                "end_iso": slot_end.isoformat(),
                "start_time": current.strftime("%H:%M"),
                "end_time": slot_end.strftime("%H:%M"),
                "date": target_date.isoformat()
            })
            current += timedelta(minutes=duration_minutes)
        
        # Filter out busy slots
        available = []
        for slot in all_slots:
            is_busy = False
            for event in self.events:
                try:
                    event_start = datetime.fromisoformat(event["start"])
                    event_end = datetime.fromisoformat(event["end"])
                    # Check overlap
                    if not (slot["end"] <= event_start or slot["start"] >= event_end):
                        is_busy = True
                        break
                except Exception as e:
                    logger.warning(f"Failed to parse event time: {e}")
                    continue
            if not is_busy:
                available.append(slot)
        
        logger.info(f"Available slots for {date_str}: {len(available)}/{len(all_slots)}")
        return available
    
    def check_availability(self, start_iso: str, end_iso: str) -> bool:
        """Check if slot is free"""
        try:
            start = datetime.fromisoformat(start_iso)
            end = datetime.fromisoformat(end_iso)
            for event in self.events:
                event_start = datetime.fromisoformat(event["start"])
                event_end = datetime.fromisoformat(event["end"])
                if not (end <= event_start or start >= event_end):
                    return False
            return True
        except Exception as e:
            logger.error(f"Availability check failed: {e}")
            return False
    
    def book_slot(self, start_iso: str, end_iso: str, summary: str, description: str = "", attendee_email: str = "", attendee_name: str = "") -> Dict:
        """Book a slot - confirm-before-write already done by agent"""
        if not self.check_availability(start_iso, end_iso):
            return {"success": False, "error": "Slot not available - already booked"}
        
        event_id = f"mock_{self.next_id}"
        self.next_id += 1
        
        event = {
            "id": event_id,
            "summary": summary,
            "description": description,
            "start": start_iso,
            "end": end_iso,
            "attendee_name": attendee_name,
            "attendee_email": attendee_email,
            "status": "confirmed",
            "created_at": datetime.now(self.timezone).isoformat(),
            "calendar_id": "mock_calendar",
            "htmlLink": f"https://calendar.google.com/calendar/event?eid={event_id} (mock)",
            "timezone": TIMEZONE,
            "client_timezone": "Europe/Tallinn (logged)"
        }
        self.events.append(event)
        logger.info(f"Booked slot {event_id}: {start_iso} - {end_iso} for {attendee_name}")
        return {"success": True, "event": event}
    
    def cancel_slot(self, event_id: str) -> Dict:
        for i, event in enumerate(self.events):
            if event["id"] == event_id:
                del self.events[i]
                logger.info(f"Cancelled event {event_id}")
                return {"success": True, "cancelled_id": event_id}
        return {"success": False, "error": f"Event {event_id} not found"}
    
    def list_events(self, days_ahead: int = 7) -> List[Dict]:
        now = datetime.now(self.timezone)
        future = now + timedelta(days=days_ahead)
        result = []
        for event in self.events:
            try:
                event_start = datetime.fromisoformat(event["start"])
                if now <= event_start <= future:
                    result.append(event)
            except:
                continue
        return sorted(result, key=lambda x: x["start"])

# Global mock instance
mock_calendar = MockCalendar()

class GoogleCalendarClient:
    def __init__(self, calendar_id: str = GOOGLE_CALENDAR_ID, credentials_path: str = GOOGLE_CREDENTIALS_PATH):
        self.calendar_id = calendar_id
        self.credentials_path = credentials_path
        self.service = None
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
            scopes = ['https://www.googleapis.com/auth/calendar']
            creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
            self.service = build('calendar', 'v3', credentials=creds)
            logger.info(f"Google Calendar client initialized for {calendar_id}")
        except Exception as e:
            logger.error(f"Failed to init Google Calendar, fallback to mock: {e}")
            self.service = None
    
    def get_available_slots(self, date_str: str, duration_minutes: int = SLOT_DURATION) -> List[Dict]:
        if not self.service:
            return mock_calendar.get_available_slots(date_str, duration_minutes)
        
        # Real implementation would query Google Calendar free/busy
        # For brevity, use mock logic but with real API for booking
        return mock_calendar.get_available_slots(date_str, duration_minutes)
    
    def check_availability(self, start_iso: str, end_iso: str) -> bool:
        if not self.service:
            return mock_calendar.check_availability(start_iso, end_iso)
        
        try:
            # Use freebusy API
            body = {
                "timeMin": start_iso,
                "timeMax": end_iso,
                "items": [{"id": self.calendar_id}]
            }
            result = self.service.freebusy().query(body=body).execute()
            busy = result["calendars"][self.calendar_id]["busy"]
            return len(busy) == 0
        except Exception as e:
            logger.error(f"Freebusy check failed: {e}")
            return False
    
    def book_slot(self, start_iso: str, end_iso: str, summary: str, description: str = "", attendee_email: str = "", attendee_name: str = "") -> Dict:
        if not self.service:
            return mock_calendar.book_slot(start_iso, end_iso, summary, description, attendee_email, attendee_name)
        
        try:
            event = {
                'summary': summary,
                'description': f"{description}\n\nAttendee: {attendee_name} ({attendee_email})\nTimezone: {TIMEZONE} (calendar) / Client: Europe/Tallinn (logged)",
                'start': {'dateTime': start_iso, 'timeZone': TIMEZONE},
                'end': {'dateTime': end_iso, 'timeZone': TIMEZONE},
                'attendees': [{'email': attendee_email}] if attendee_email else []
            }
            created = self.service.events().insert(calendarId=self.calendar_id, body=event).execute()
            logger.info(f"Booked real Google Calendar event {created['id']}")
            return {"success": True, "event": created}
        except Exception as e:
            logger.error(f"Failed to book Google Calendar: {e}")
            return {"success": False, "error": str(e)}
    
    def cancel_slot(self, event_id: str) -> Dict:
        if not self.service:
            return mock_calendar.cancel_slot(event_id)
        try:
            self.service.events().delete(calendarId=self.calendar_id, eventId=event_id).execute()
            return {"success": True, "cancelled_id": event_id}
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return {"success": False, "error": str(e)}

def get_calendar_client():
    if USE_MOCK_CALENDAR:
        logger.info("Using Mock Calendar (no Google credentials)")
        return mock_calendar
    else:
        return GoogleCalendarClient()

# Function calling tools for LLM
CALENDAR_FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check available time slots for a given date. Use this when user wants to book appointment and you need to see free slots. Handles timezone explicitly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format, e.g., 2024-09-30"},
                    "duration_minutes": {"type": "integer", "description": "Duration in minutes, default 60", "default": 60},
                    "client_timezone": {"type": "string", "description": "Client timezone, e.g., Europe/Tallinn, for logging"}
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_slot",
            "description": "Book a slot in calendar. ONLY call after explicit confirmation from user (confirm-before-write). Logs both calendar and client timezone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_iso": {"type": "string", "description": "Start time in ISO format with timezone, e.g., 2024-09-30T10:00:00+03:00"},
                    "end_iso": {"type": "string", "description": "End time in ISO format"},
                    "summary": {"type": "string", "description": "Event summary, e.g., 'Wellness appointment - Anna Schmidt'"},
                    "description": {"type": "string", "description": "Event description with details"},
                    "attendee_name": {"type": "string", "description": "Client name"},
                    "attendee_email": {"type": "string", "description": "Client email if available"},
                    "client_timezone": {"type": "string", "description": "Client timezone for logging"}
                },
                "required": ["start_iso", "end_iso", "summary", "attendee_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_slot",
            "description": "Cancel an existing booking by event ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "Event ID to cancel"}
                },
                "required": ["event_id"]
            }
        }
    }
]

def handle_function_call(function_name: str, arguments: dict) -> dict:
    """
    Execute calendar function called by LLM
    Logs timezone explicitly
    """
    client = get_calendar_client()
    
    # Log timezone info
    client_tz = arguments.get("client_timezone", "unknown")
    logger.info(f"Function call {function_name} with client_timezone={client_tz}, calendar_timezone={TIMEZONE}")
    
    if function_name == "check_availability":
        date_str = arguments.get("date")
        duration = arguments.get("duration_minutes", SLOT_DURATION)
        slots = client.get_available_slots(date_str, duration)
        return {
            "available_slots": slots,
            "date": date_str,
            "count": len(slots),
            "calendar_timezone": TIMEZONE,
            "client_timezone": client_tz,
            "message": f"Found {len(slots)} available slots for {date_str} in timezone {TIMEZONE} (client: {client_tz})"
        }
    
    elif function_name == "book_slot":
        # Confirm-before-write is enforced by agent, not here, but we log
        result = client.book_slot(
            start_iso=arguments.get("start_iso"),
            end_iso=arguments.get("end_iso"),
            summary=arguments.get("summary"),
            description=arguments.get("description", "") + f"\nClient TZ: {client_tz}, Calendar TZ: {TIMEZONE}",
            attendee_name=arguments.get("attendee_name"),
            attendee_email=arguments.get("attendee_email", "")
        )
        result["timezone_logged"] = {"calendar": TIMEZONE, "client": client_tz}
        return result
    
    elif function_name == "cancel_slot":
        result = client.cancel_slot(arguments.get("event_id"))
        return result
    
    else:
        return {"success": False, "error": f"Unknown function {function_name}"}

if __name__ == "__main__":
    # Test mock calendar
    cal = MockCalendar()
    print("Available slots tomorrow:")
    tomorrow = (datetime.now(pytz.timezone(TIMEZONE)) + timedelta(days=1)).strftime("%Y-%m-%d")
    slots = cal.get_available_slots(tomorrow)
    for s in slots[:3]:
        print(f"  {s['start_time']}-{s['end_time']} {s['start_iso']}")
    
    print("\nBooking first slot:")
    if slots:
        result = cal.book_slot(slots[0]["start_iso"], slots[0]["end_iso"], "Test Booking - Anna", "Test", attendee_name="Anna Schmidt")
        print(result)
    
    print("\nEvents:")
    for e in cal.list_events():
        print(f"  {e['id']}: {e['summary']} {e['start']}")
