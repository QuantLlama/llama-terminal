import sys
from datetime import datetime, timedelta

def test():
    expanded_filter = ["USD"]
    events = []
    data = [{"title":"ISM Manufacturing PMI","country":"USD","date":"2026-04-01T10:00:00-04:00","impact":"High","forecast":"52.3","previous":"52.4"}]
    now = datetime.now()
    for event_data in data:
        try:
            event_time_str = event_data.get("date", "")
            country = event_data.get("country", "USD").upper()
            event_name = event_data.get("title", "Economic Event")
            impact_level = "High"
            forecast = ""
            previous = ""
            actual = ""
            
            event_date = now + timedelta(hours=1)
            if event_time_str:
                try:
                    event_date = datetime.fromisoformat(event_time_str)
                except:
                    pass
            
            if (
                event_date.date() >= (now - timedelta(days=7)).date()
                and country.upper() in expanded_filter
            ):
                local_event_date = event_date
                if local_event_date.tzinfo is not None:
                    local_event_date = local_event_date.astimezone()
                    
                events.append(
                    {
                        "id": f"id",
                        "date": event_date.isoformat(),
                        "is_today": local_event_date.date() == now.astimezone().date() if now.tzinfo else local_event_date.date() == now.date(),
                    }
                )
                print(events[-1])
        except Exception as e:
            print(f"Exception for {event_data}: {e}")
            import traceback; traceback.print_exc()

test()
