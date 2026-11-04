"""
A tool-using agent with real validation and informative errors.

The point of this lab is not that it works — it is that you will break it
on purpose and watch which layer catches the damage.

Run:  python tools_lab.py
"""

import datetime
import json

from runtime import make_client

client = make_client()

MODEL = "claude-opus-5"
MAX_STEPS = 10

# In-memory "systems of record". A real agent would hit a calendar API.
PEOPLE = {
    "ana": {"name": "Ana Ruiz", "timezone": "Europe/Madrid", "role": "engineer"},
    "ben": {"name": "Ben Okafor", "timezone": "America/New_York", "role": "designer"},
    "cai": {"name": "Cai Liu", "timezone": "Asia/Singapore", "role": "manager"},
}

BUSY = {  # person -> list of (date, start_hour, end_hour) in 24h local time
    "ana": [("2026-04-06", 9, 11), ("2026-04-07", 14, 16)],
    "ben": [("2026-04-06", 13, 15)],
    "cai": [("2026-04-06", 9, 10), ("2026-04-07", 9, 12)],
}

BOOKED = []  # meetings this agent has created


# ---------------------------------------------------------------------------
# TOOL IMPLEMENTATIONS
# Each one validates its own inputs and returns an informative error rather
# than raising. Errors are observations the agent can act on.
# ---------------------------------------------------------------------------

def find_person(query: str) -> dict:
    """Resolve a name or nickname to a person record."""
    key = query.strip().lower()
    if key in PEOPLE:
        return {"id": key, **PEOPLE[key]}

    matches = [k for k, v in PEOPLE.items() if key in v["name"].lower()]
    if len(matches) == 1:
        return {"id": matches[0], **PEOPLE[matches[0]]}
    if len(matches) > 1:
        return {"error": f"'{query}' matches several people: {matches}. Be more specific."}
    return {
        "error": f"No person matching '{query}'. "
                 f"Known ids: {sorted(PEOPLE)}. Use one of those ids."
    }


def check_availability(person_id: str, date: str) -> dict:
    """Return the busy blocks for one person on one day."""
    if person_id not in PEOPLE:
        return {"error": f"Unknown person_id '{person_id}'. Call find_person first. "
                         f"Valid ids: {sorted(PEOPLE)}."}
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        return {"error": f"date must be ISO format YYYY-MM-DD, got '{date}'."}

    blocks = [
        {"start_hour": s, "end_hour": e}
        for (d, s, e) in BUSY.get(person_id, []) if d == date
    ]
    return {
        "person_id": person_id,
        "date": date,
        "busy_blocks": blocks,
        "working_hours": {"start_hour": 9, "end_hour": 18},
    }


def book_meeting(person_ids: list, date: str, start_hour: int, duration_hours: int,
                 title: str) -> dict:
    """Create a meeting. This one has side effects, so validation is strict."""
    # --- validation gate: nothing is written until every check passes
    if not isinstance(person_ids, list) or not person_ids:
        return {"error": "person_ids must be a non-empty list of person ids."}

    unknown = [p for p in person_ids if p not in PEOPLE]
    if unknown:
        return {"error": f"Unknown person_ids: {unknown}. Valid ids: {sorted(PEOPLE)}."}

    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        return {"error": f"date must be ISO format YYYY-MM-DD, got '{date}'."}

    if not (isinstance(start_hour, int) and 9 <= start_hour <= 17):
        return {"error": f"start_hour must be an integer between 9 and 17, got {start_hour}."}

    if not (isinstance(duration_hours, int) and 1 <= duration_hours <= 4):
        return {"error": f"duration_hours must be an integer between 1 and 4, "
                         f"got {duration_hours}."}

    # A field being 'required' in the schema does NOT mean it arrived usable.
    # The schema says the model must send a title; only this check says it must
    # be a non-empty one.
    if not isinstance(title, str) or not title.strip():
        return {"error": "title must be a non-empty string describing the meeting."}

    end_hour = start_hour + duration_hours
    if end_hour > 18:
        return {"error": f"Meeting would end at {end_hour}:00, past the 18:00 working "
                         f"limit. Choose an earlier start_hour or shorter duration."}

    # --- conflict check
    conflicts = []
    for person in person_ids:
        for (d, s, e) in BUSY.get(person, []):
            if d == date and start_hour < e and end_hour > s:
                conflicts.append({"person_id": person, "busy": f"{s}:00-{e}:00"})
    if conflicts:
        return {"error": f"Conflicts found: {conflicts}. Pick a different slot."}

    # --- only now do we write
    meeting = {
        "id": f"mtg-{len(BOOKED) + 1}",
        "title": title,
        "attendees": person_ids,
        "date": date,
        "start_hour": start_hour,
        "end_hour": end_hour,
    }
    BOOKED.append(meeting)
    for person in person_ids:
        BUSY.setdefault(person, []).append((date, start_hour, end_hour))
    return {"booked": meeting}


TOOL_FUNCTIONS = {
    "find_person": find_person,
    "check_availability": check_availability,
    "book_meeting": book_meeting,
}


# ---------------------------------------------------------------------------
# TOOL DEFINITIONS — the descriptions are prompts. Read them as prompts.
# ---------------------------------------------------------------------------

TOOL_SPECS = [
    {
        "name": "find_person",
        "description": (
            "Resolve a person's name or nickname to their internal id, timezone "
            "and role. Call this first whenever the user refers to a person by "
            "name, before any other tool that needs a person_id. It matches on "
            "id or on full name; it cannot search by role or team."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A person's id, first name, or full name.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_availability",
        "description": (
            "Return the busy time blocks for one person on one specific day, "
            "plus their working hours. Use this to find a free slot before "
            "booking. It covers one person and one day per call — call it "
            "repeatedly for several people. It does not suggest slots; you "
            "must compare the results yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "description": "Internal id from find_person, e.g. 'ana'.",
                },
                "date": {
                    "type": "string",
                    "description": "The day to check, ISO format YYYY-MM-DD.",
                },
            },
            "required": ["person_id", "date"],
        },
    },
    {
        "name": "book_meeting",
        "description": (
            "Create a meeting on the shared calendar. This writes real data and "
            "notifies attendees, so only call it once you have confirmed every "
            "attendee is free using check_availability. Meetings must fall "
            "inside 09:00-18:00 and last 1 to 4 hours. It rejects any slot that "
            "conflicts with an existing commitment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "person_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Attendee ids from find_person.",
                },
                "date": {"type": "string", "description": "ISO date YYYY-MM-DD."},
                "start_hour": {
                    "type": "integer",
                    "description": "Start hour in 24h local time, 9 to 17.",
                },
                "duration_hours": {
                    "type": "integer",
                    "description": "Length in whole hours, 1 to 4.",
                },
                "title": {"type": "string", "description": "Short meeting title."},
            },
            "required": ["person_ids", "date", "start_hour", "duration_hours", "title"],
        },
    },
]


# ---------------------------------------------------------------------------
# THE LOOP
# ---------------------------------------------------------------------------

def run_agent(goal: str) -> str:
    messages = [{"role": "user", "content": goal}]
    tool_calls = 0

    for step in range(1, MAX_STEPS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},
            tools=TOOL_SPECS,
            messages=messages,
        )

        for block in response.content:
            if block.type == "text" and block.text.strip():
                print(f"\n[step {step}] {block.text.strip()}")

        if response.stop_reason != "tool_use":
            final = "".join(b.text for b in response.content if b.type == "text")
            print(f"\n{'=' * 60}\nDONE in {step} steps, {tool_calls} tool calls")
            print(f"Meetings booked: {json.dumps(BOOKED, indent=2)}")
            return final.strip()

        messages.append({"role": "assistant", "content": response.content})

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_calls += 1
            print(f"  -> {block.name}({json.dumps(block.input)})")
            function = TOOL_FUNCTIONS.get(block.name)
            if function is None:
                output = {"error": f"Unknown tool {block.name}"}
            else:
                try:
                    output = function(**block.input)
                except TypeError as exc:
                    # Wrong argument names or count. Tell the model precisely.
                    output = {"error": f"Bad arguments for {block.name}: {exc}"}
                except Exception as exc:  # noqa: BLE001
                    output = {"error": f"{type(exc).__name__}: {exc}"}
            marker = "ERR " if "error" in output else "OK  "
            print(f"     {marker}{json.dumps(output)}")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output),
                "is_error": "error" in output,
            })

        messages.append({"role": "user", "content": results})

    return "Stopped: step limit reached"


if __name__ == "__main__":
    run_agent(
        "Book a 2-hour design review with Ana, Ben and Cai on 2026-04-06. "
        "Find a slot that works for all three."
    )
