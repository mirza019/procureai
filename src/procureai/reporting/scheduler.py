from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from procureai.db.models import ReportSchedule, Role
from procureai.db.session import SessionLocal
from procureai.reporting.intelligent import generate_report, monthly_period, weekly_period
from procureai.schemas.reporting import ReportRequest, ReportType


def run_scheduled_report(schedule_id) -> None:
    with SessionLocal() as db:
        schedule = db.get(ReportSchedule, schedule_id)
        if not schedule or not schedule.enabled:
            return
        today = datetime.now(UTC).date()
        start, end = (
            weekly_period(today)
            if schedule.report_type == ReportType.WEEKLY.value
            else monthly_period(today)
        )
        asyncio.run(
            generate_report(
                db,
                ReportRequest(
                    report_type=ReportType(schedule.report_type),
                    audience_role=Role(schedule.audience_role),
                    period_start=start,
                    period_end=end,
                ),
                timezone=schedule.timezone,
            )
        )


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    with SessionLocal() as db:
        for schedule in db.query(ReportSchedule).filter_by(enabled=True):
            scheduler.add_job(
                run_scheduled_report,
                CronTrigger.from_crontab(schedule.cron_expression, timezone=schedule.timezone),
                args=[schedule.schedule_id],
                id=f"report-{schedule.schedule_id}",
                replace_existing=True,
            )
    return scheduler
