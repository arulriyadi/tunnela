"""
Rolling 24h snapshots for Clients network overview metrics (Postgres / SQLite / MySQL via wgdashboard DB).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

import sqlalchemy as db

from .ConnectionString import ConnectionString

if TYPE_CHECKING:
    from .WireguardConfiguration import WireguardConfiguration


class ClientsNetworkOverviewStats:
    """
    Persists one JSON metrics blob per collection tick; deletes rows older than 24 hours.
    """

    RETENTION_HOURS = 24
    INTERVAL_MIN_MS = 60_000
    INTERVAL_MAX_MS = 3_600_000
    INTERVAL_DEFAULT_MS = 300_000

    def __init__(self, dashboard_config: Any = None):
        self._dashboard_config = dashboard_config
        self.engine = db.create_engine(ConnectionString("wgdashboard"))
        self.metadata = db.MetaData()
        self.snapshots = db.Table(
            "clients_network_overview_snapshots",
            self.metadata,
            db.Column("snapshot_id", db.String(36), primary_key=True),
            db.Column(
                "recorded_at",
                db.DateTime(timezone=True),
                nullable=False,
                server_default=db.func.now(),
            ),
            db.Column("metrics", db.JSON, nullable=False),
            db.Index("ix_clients_network_overview_snapshots_recorded_at", "recorded_at"),
            extend_existing=True,
        )
        self.metadata.create_all(self.engine)

    @staticmethod
    def clamp_interval_ms(ms: int) -> int:
        """Clamp collection interval to 1 min … 1 hour (milliseconds)."""
        return max(
            ClientsNetworkOverviewStats.INTERVAL_MIN_MS,
            min(int(ms), ClientsNetworkOverviewStats.INTERVAL_MAX_MS),
        )

    @staticmethod
    def get_interval_ms(dashboard_config: Any) -> int:
        """Clients statistics job interval; clamped 1 min … 1 hour (ms)."""
        if dashboard_config is None:
            return ClientsNetworkOverviewStats.INTERVAL_DEFAULT_MS
        exist, raw = dashboard_config.GetConfig("Server", "clients_statistics_interval")
        if not exist or raw is None or str(raw).strip() == "":
            return ClientsNetworkOverviewStats.INTERVAL_DEFAULT_MS
        try:
            val = int(str(raw).strip())
        except (TypeError, ValueError):
            return ClientsNetworkOverviewStats.INTERVAL_DEFAULT_MS
        return ClientsNetworkOverviewStats.clamp_interval_ms(val)

    @staticmethod
    def build_metrics(
        wireguard_configurations: dict[str, WireguardConfiguration],
    ) -> dict[str, Any]:
        active_connections = 0
        total_peers = 0
        total_receive_gb = 0.0
        total_sent_gb = 0.0
        configurations: list[dict[str, Any]] = []

        for wc in wireguard_configurations.values():
            if wc is None:
                continue
            peers = list(wc.Peers) + list(wc.getRestrictedPeersList())
            n_active = sum(1 for p in peers if getattr(p, "status", None) == "running")
            n_total = len(peers)
            active_connections += n_active
            total_peers += n_total
            cfg_rx = sum(
                float(getattr(p, "cumu_receive", 0) or 0)
                + float(getattr(p, "total_receive", 0) or 0)
                for p in peers
            )
            cfg_tx = sum(
                float(getattr(p, "cumu_sent", 0) or 0)
                + float(getattr(p, "total_sent", 0) or 0)
                for p in peers
            )
            total_receive_gb += cfg_rx
            total_sent_gb += cfg_tx
            configurations.append(
                {
                    "name": wc.Name,
                    "active": n_active,
                    "total": n_total,
                    "receive_gb": round(cfg_rx, 6),
                    "sent_gb": round(cfg_tx, 6),
                }
            )

        return {
            "active_connections": active_connections,
            "total_peers": total_peers,
            "total_receive_gb": round(total_receive_gb, 6),
            "total_sent_gb": round(total_sent_gb, 6),
            "connections_24h": None,
            "network_load_percent": None,
            "configurations": configurations,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    def persist_snapshot(self, metrics: dict[str, Any]) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.RETENTION_HOURS)
        with self.engine.begin() as conn:
            conn.execute(
                self.snapshots.insert().values(
                    snapshot_id=str(uuid.uuid4()),
                    metrics=metrics,
                )
            )
            conn.execute(self.snapshots.delete().where(self.snapshots.c.recorded_at < cutoff))

    def collect_and_persist(
        self,
        wireguard_configurations: dict[str, WireguardConfiguration],
    ) -> dict[str, Any]:
        metrics = self.build_metrics(wireguard_configurations)
        self.persist_snapshot(metrics)
        return metrics

    def get_overview_for_api(self) -> dict[str, Any]:
        """Latest snapshot + all snapshots in the retention window (for chart)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.RETENTION_HOURS)
        with self.engine.connect() as conn:
            latest_row = (
                conn.execute(
                    db.select(self.snapshots)
                    .order_by(self.snapshots.c.recorded_at.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            series_rows = (
                conn.execute(
                    db.select(self.snapshots)
                    .where(self.snapshots.c.recorded_at >= cutoff)
                    .order_by(self.snapshots.c.recorded_at.asc())
                )
                .mappings()
                .all()
            )

        def row_to_point(r: Any) -> dict[str, Any]:
            ra = r["recorded_at"]
            ra_out = ra.isoformat() if hasattr(ra, "isoformat") else str(ra)
            return {
                "snapshot_id": r["snapshot_id"],
                "recorded_at": ra_out,
                "metrics": r["metrics"],
            }

        return {
            "latest": row_to_point(latest_row) if latest_row else None,
            "series24h": [row_to_point(r) for r in series_rows],
        }
