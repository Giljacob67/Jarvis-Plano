from datetime import date
from fastapi import APIRouter

from app.schemas import DayOverview, CalendarEvent, Task, Email

router = APIRouter()


@router.get("/day", response_model=DayOverview)
async def get_day_overview() -> DayOverview:
    today = date.today().isoformat()

    return DayOverview(
        date=today,
        calendar=[
            CalendarEvent(title="Daily standup", start="09:00", end="09:30", location="Google Meet"),
            CalendarEvent(title="Sprint review", start="14:00", end="15:00", location="Zoom"),
            CalendarEvent(title="Lunch with client", start="12:00", end="13:00", location="Restaurante Central"),
        ],
        tasks=[
            Task(title="Review PR #42", due=today, status="pending"),
            Task(title="Write API docs", due=today, status="in_progress"),
            Task(title="Deploy staging", due=today, status="done"),
        ],
        emails=[
            Email(subject="Quarterly report ready", sender="cfo@company.com", snippet="The Q1 report is attached...", priority="high"),
            Email(subject="Team offsite planning", sender="hr@company.com", snippet="Please vote on the dates...", priority="normal"),
            Email(subject="Invoice #1234", sender="billing@vendor.com", snippet="Your invoice is due on...", priority="low"),
        ],
    )
