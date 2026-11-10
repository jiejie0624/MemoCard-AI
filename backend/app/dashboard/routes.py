from typing import Annotated
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.auth.routes import PublicUser, current_user
from backend.app.calendar.repository import CalendarRepository


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardSummary(BaseModel):
    timezone: str
    today: date
    overdue_count: int
    today_count: int
    upcoming_count: int
    next_review_at: datetime | None


def get_dashboard_repository() -> CalendarRepository:
    return CalendarRepository()


Repository = Annotated[CalendarRepository, Depends(get_dashboard_repository)]
AuthenticatedUser = Annotated[PublicUser, Depends(current_user)]


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(user: AuthenticatedUser, repository: Repository) -> dict:
    try:
        ZoneInfo(user.timezone)
        summary = repository.get_summary(user.id, user.timezone)
        return {**summary, "timezone": user.timezone}
    except (ZoneInfoNotFoundError, TypeError) as error:
        raise HTTPException(status_code=500, detail="账号时区配置无效") from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="学习摘要暂时无法加载") from error
