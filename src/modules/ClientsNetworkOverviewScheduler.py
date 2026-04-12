"""
APScheduler job: collect Clients network overview metrics into Postgres (rolling 24h).
Started once per Gunicorn worker; stock config uses workers=1.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .ClientsNetworkOverviewStats import ClientsNetworkOverviewStats

_scheduler: BackgroundScheduler | None = None
JOB_ID = "clients_network_overview_stats"


def _run_collect(app: Any) -> None:
    import dashboard as dashboard_module

    with app.app_context():
        try:
            dashboard_module.InitWireguardConfigurationsList()
            dashboard_module.ClientsNetworkOverviewStatsManager.collect_and_persist(
                dashboard_module.WireguardConfigurations
            )
        except Exception:
            dashboard_module.app.logger.error(
                "[ClientsNetworkOverview] Collection error",
                exc_info=True,
            )


def start_clients_network_overview_scheduler(app: Any) -> None:
    global _scheduler
    import dashboard as dashboard_module

    if _scheduler is not None:
        return

    sec = max(
        60,
        ClientsNetworkOverviewStats.get_interval_ms(dashboard_module.DashboardConfig) // 1000,
    )
    _scheduler = BackgroundScheduler(daemon=True, timezone="UTC")

    def job() -> None:
        _run_collect(app)

    _scheduler.add_job(
        job,
        trigger=IntervalTrigger(seconds=sec),
        id=JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=max(120, sec),
        next_run_time=datetime.now(timezone.utc),
    )
    _scheduler.start()
    dashboard_module.app.logger.info(
        f"[ClientsNetworkOverview] Scheduler started (every {sec}s)"
    )


def reschedule_clients_network_overview_job() -> None:
    """Call after updating `clients_statistics_interval` in dashboard config (e.g. Settings save)."""
    global _scheduler
    import dashboard as dashboard_module

    if _scheduler is None:
        return
    sec = max(
        60,
        ClientsNetworkOverviewStats.get_interval_ms(dashboard_module.DashboardConfig) // 1000,
    )
    try:
        _scheduler.reschedule_job(
            JOB_ID,
            trigger=IntervalTrigger(seconds=sec),
        )
        dashboard_module.app.logger.info(
            f"[ClientsNetworkOverview] Rescheduled to every {sec}s"
        )
    except Exception:
        dashboard_module.app.logger.error(
            "[ClientsNetworkOverview] Reschedule failed",
            exc_info=True,
        )


def shutdown_clients_network_overview_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
