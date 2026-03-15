from pydantic import BaseModel


class CalendarEvent(BaseModel):
    title: str
    start: str
    end: str
    location: str = ""


class Task(BaseModel):
    title: str
    due: str = ""
    status: str = "pending"


class Email(BaseModel):
    subject: str
    sender: str
    snippet: str
    priority: str = "normal"


class DayOverview(BaseModel):
    date: str
    calendar: list[CalendarEvent]
    tasks: list[Task]
    emails: list[Email]
