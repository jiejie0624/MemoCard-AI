from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.app.auth.routes import PublicUser, current_user
from backend.app.calendar.repository import CalendarRepository


router = APIRouter(prefix="/revisions", tags=["revisions"])


class DayCount(BaseModel):
    date: date
    count: int


class CalendarResponse(BaseModel):
    timezone: str
    from_date: date
    to_date: date
    days: list[DayCount]


class DayCardSource(BaseModel):
    id: UUID
    name: str


class DayCard(BaseModel):
    id: UUID
    question: str
    answer: str
    next_review_at: datetime
    sources: list[DayCardSource]


class DayCardsResponse(BaseModel):
    date: date
    cards: list[DayCard]


def get_calendar_repository() -> CalendarRepository:
    return CalendarRepository()


Repository = Annotated[CalendarRepository, Depends(get_calendar_repository)]
AuthenticatedUser = Annotated[PublicUser, Depends(current_user)]


def _check_timezone(timezone_name: str) -> None:
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError) as error:
        raise HTTPException(status_code=500, detail="账号时区配置无效") from error


@router.get("", response_model=CalendarResponse)
def get_revision_calendar(
    user: AuthenticatedUser,
    repository: Repository,
    start_date: Annotated[date, Query(alias="from")],
    end_date: Annotated[date, Query(alias="to")],
) -> dict:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="结束日期必须晚于或等于开始日期")
    if (end_date - start_date).days >= 42:
        raise HTTPException(status_code=422, detail="一次最多查询 42 天的日历数据")
    _check_timezone(user.timezone)
    try:
        counts = {
            row["due_date"]: row["card_count"]
            for row in repository.get_day_counts(user.id, user.timezone, start_date, end_date)
        }
        days = []
        current = start_date
        while current <= end_date:
            days.append({"date": current, "count": counts.get(current, 0)})
            current += timedelta(days=1)
        return {"timezone": user.timezone, "from_date": start_date, "to_date": end_date, "days": days}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=503, detail="复习日历暂时无法加载") from error


@router.get("/day", response_model=DayCardsResponse)
def get_revision_day(
    user: AuthenticatedUser,
    repository: Repository,
    due_date: Annotated[date, Query(alias="date")],
) -> dict:
    _check_timezone(user.timezone)
    try:
        cards = repository.get_day_cards(user.id, user.timezone, due_date)
        return {"date": due_date, "cards": cards}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=503, detail="当天复习内容暂时无法加载") from error
