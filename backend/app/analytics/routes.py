from __future__ import annotations

import logging
from datetime import date
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.analytics.repository import AnalyticsRepository
from backend.app.auth.routes import PublicUser, current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


class MasteryDistribution(BaseModel):
    new: int
    learning: int
    mastered: int


class UpcomingDay(BaseModel):
    date: date
    count: int


class AnalyticsSummary(BaseModel):
    timezone: str
    reviewed_total: int
    # None when there are too few reviews for a percentage to mean anything.
    correct_rate: float | None
    streak_days: int
    mastery: MasteryDistribution
    upcoming: list[UpcomingDay]


def get_analytics_repository() -> AnalyticsRepository:
    return AnalyticsRepository()


Repository = Annotated[AnalyticsRepository, Depends(get_analytics_repository)]
AuthenticatedUser = Annotated[PublicUser, Depends(current_user)]


@router.get("/summary", response_model=AnalyticsSummary)
def get_analytics_summary(user: AuthenticatedUser, repository: Repository) -> dict:
    try:
        # Day boundaries come from the account's zone, so the same query means the same
        # thing regardless of where the server runs.
        ZoneInfo(user.timezone)
        summary = repository.get_summary(user.id, user.timezone)
        return {**summary, "timezone": user.timezone}
    except (ZoneInfoNotFoundError, TypeError) as error:
        raise HTTPException(status_code=500, detail="账号时区配置无效") from error
    except Exception as error:
        logger.warning("Learning data could not be loaded (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="学习数据暂时无法加载") from error
