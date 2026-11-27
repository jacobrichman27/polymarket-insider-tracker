"""The collaborators a ``Pipeline`` runs on, and how the production set is assembled.

``Pipeline`` orchestrates; this module owns what it orchestrates. A caller that embeds the
pipeline over its own connections (or substitutes a collaborator) builds a ``PipelineComponents``
and installs it with ``Pipeline.install_components``; ``Pipeline.start`` builds the production
set from ``Settings`` with ``build_components`` when nothing was installed.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeVar

from redis.asyncio import Redis

from polymarket_insider_tracker.alerter.channels.discord import DiscordChannel
from polymarket_insider_tracker.alerter.channels.telegram import TelegramChannel
from polymarket_insider_tracker.alerter.dispatcher import AlertChannel, AlertDispatcher
from polymarket_insider_tracker.alerter.formatter import AlertFormatter
from polymarket_insider_tracker.alerter.history import AlertHistory
from polymarket_insider_tracker.config import Settings
from polymarket_insider_tracker.detector.detector_config import capture_detector_config
from polymarket_insider_tracker.detector.evaluation import SizeEvaluation, WalletEvaluation
from polymarket_insider_tracker.detector.fresh_wallet import FreshWalletDetector
from polymarket_insider_tracker.detector.scorer import RiskScorer
from polymarket_insider_tracker.detector.scoring_config import DetectorConfig
from polymarket_insider_tracker.detector.size_anomaly import SizeAnomalyDetector
from polymarket_insider_tracker.ingestor.archive import gap_ledger
from polymarket_insider_tracker.ingestor.archive.health import ArchiveHealthSignals
from polymarket_insider_tracker.ingestor.archive.metrics import PrometheusArchiveMetrics
from polymarket_insider_tracker.ingestor.archive.workers import MarketWarmCoordinator
from polymarket_insider_tracker.ingestor.archive.writer import (
    ArchiveMetrics,
    ArchiveWriter,
    ArchiveWriteStatus,
)
from polymarket_insider_tracker.ingestor.clob_client import ClobClient
from polymarket_insider_tracker.ingestor.metadata_sync import MarketMetadataSync
from polymarket_insider_tracker.ingestor.models import TradeEvent
from polymarket_insider_tracker.ingestor.observation_boundary import (
    LossEvent,
)
from polymarket_insider_tracker.ingestor.observation_boundary import (
    source_id as boundary_source_id,
)
from polymarket_insider_tracker.ingestor.trade_poller import IngestionState, TradePoller
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation
from polymarket_insider_tracker.profiler.analyzer import WalletAnalyzer
from polymarket_insider_tracker.profiler.chain import PolygonClient
from polymarket_insider_tracker.profiler.funding import FundingTracer
from polymarket_insider_tracker.storage.database import DatabaseManager

logger = logging.getLogger("polymarket_insider_tracker.pipeline")

_EvaluationT = TypeVar("_EvaluationT", covariant=True)


class Evaluator(Protocol[_EvaluationT]):
    """A detector the pipeline evaluates a trade with (satisfied by the real detectors)."""

    @abstractmethod
    async def evaluate(self, trade: TradeEvent, *, evaluated_at: datetime) -> _EvaluationT:
        """Evaluate ``trade`` as of ``evaluated_at``."""


class Pingable(Protocol):
    """Protocol for health ping check on Redis."""

    @abstractmethod
    def ping(self) -> Awaitable[bool] | bool:
        """Send ``PING``."""


async def ping_redis(client: Pingable) -> None:
    """Await a ``PING``; redis-py types the reply as an awaitable-or-value union."""
    reply = client.ping()
    if not inspect.isawaitable(reply):
        raise TypeError("Redis ping reply is not awaitable")
    await reply


class RedisFactory(Protocol):
    """Concrete Redis construction surface used by the pipeline."""

    @classmethod
    @abstractmethod
    def from_url(cls, url: str) -> Redis:
        """Construct a client for ``url``."""


def _redis_factory() -> type[RedisFactory]:
    """The real ``Redis`` class viewed through its typed ``from_url``."""
    return Redis


@dataclass(frozen=True)
class PipelineComponents:
    """The collaborators a pipeline processes trades with.

    ``owns_connections`` says whether the pipeline created ``redis`` and ``db_manager`` and so
    closes them when it stops; a caller that supplies its own connections keeps them open.
    """

    redis: Redis
    db_manager: DatabaseManager | None
    metadata_sync: MarketMetadataSync
    funding_tracer: FundingTracer | None
    fresh_wallet_detector: Evaluator[WalletEvaluation]
    size_anomaly_detector: Evaluator[SizeEvaluation]
    detector_config: DetectorConfig
    risk_scorer: RiskScorer
    alert_formatter: AlertFormatter
    alert_dispatcher: AlertDispatcher
    trade_poller: TradePoller | None
    owns_connections: bool = True


def _build_discord_channel(settings: Settings) -> DiscordChannel | None:
    discord = settings.discord
    if not discord.enabled or not discord.webhook_url:
        return None
    logger.info("Discord channel enabled")
    return DiscordChannel(discord.webhook_url.get_secret_value())


def _build_telegram_channel(settings: Settings) -> TelegramChannel | None:
    telegram = settings.telegram
    if not telegram.enabled or not telegram.bot_token or not telegram.chat_id:
        return None
    logger.info("Telegram channel enabled")
    return TelegramChannel(telegram.bot_token.get_secret_value(), telegram.chat_id)


def build_alert_channels(settings: Settings) -> list[AlertChannel]:
    """Build the list of alert channels the settings enable."""
    channels: list[AlertChannel] = []
    discord_chan = _build_discord_channel(settings)
    if discord_chan:
        channels.append(discord_chan)

    telegram_chan = _build_telegram_channel(settings)
    if telegram_chan:
        channels.append(telegram_chan)

    if not channels:
        logger.warning("No alert channels configured")

    return channels


async def build_components(
    settings: Settings,
    *,
    dry_run: bool,
    on_trade: Callable[[TradeEvent], Awaitable[None]],
    on_ingestion_state: Callable[[IngestionState], None],
    archive_health: ArchiveHealthSignals | None = None,
    market_warm: MarketWarmCoordinator | None = None,
) -> PipelineComponents:
    """Assemble the production collaborators from ``settings``.

    A failure part-way through closes the connections already opened before it propagates.
    """
    logger.debug("Initializing Redis connection...")
    redis = _redis_factory().from_url(settings.redis.url)
    db_manager: DatabaseManager | None = None
    try:
        logger.debug("Initializing database manager...")
        db_manager = DatabaseManager(settings.database.url, async_mode=True)
        return _assemble(
            settings,
            redis,
            db_manager,
            dry_run,
            on_trade,
            on_ingestion_state,
            archive_health,
            market_warm,
        )
    except Exception:
        if db_manager is not None:
            await db_manager.dispose_async()
        await redis.aclose()
        raise


def _assemble(
    settings: Settings,
    redis: Redis,
    db_manager: DatabaseManager,
    dry_run: bool,
    on_trade: Callable[[TradeEvent], Awaitable[None]],
    on_ingestion_state: Callable[[IngestionState], None],
    archive_health: ArchiveHealthSignals | None,
    market_warm: MarketWarmCoordinator | None,
) -> PipelineComponents:
    logger.debug("Initializing Polygon client...")
    polygon_client = PolygonClient(
        settings.polygon.rpc_url,
        fallback_rpc_url=settings.polygon.fallback_rpc_url,
        redis=redis,
    )

    logger.debug("Initializing CLOB client...")
    clob_client = ClobClient()

    logger.debug("Initializing market metadata sync...")
    metadata_sync = MarketMetadataSync(redis=redis, clob_client=clob_client)

    logger.debug("Initializing wallet analyzer...")
    wallet_analyzer = WalletAnalyzer(polygon_client, redis=redis)

    logger.debug("Initializing funding tracer...")
    funding_tracer = FundingTracer(polygon_client)

    logger.debug("Initializing detectors...")
    fresh_detector = FreshWalletDetector(wallet_analyzer)
    size_detector = SizeAnomalyDetector(metadata_sync)

    logger.debug("Initializing risk scorer...")
    risk_scorer = RiskScorer(redis, alert_threshold=settings.detector.alert_threshold)
    logger.info(
        "RiskScorer threshold=%.2f persist=%s",
        settings.detector.alert_threshold,
        settings.detector.persist_assessments,
    )

    logger.debug("Initializing alerting components...")
    alert_formatter = AlertFormatter(verbosity="detailed")
    channels = build_alert_channels(settings)
    alert_history = AlertHistory(redis, dedup_window_seconds=settings.detector.dedup_window_seconds)
    logger.info("AlertHistory dedup_window=%ds", settings.detector.dedup_window_seconds)
    alert_dispatcher = AlertDispatcher(channels, history=alert_history, dry_run=dry_run)

    logger.debug("Initializing trade poller...")
    source = boundary_source_id(
        settings.polymarket.trades_url, settings.polymarket.trades_coverage.value
    )
    archive_write = None
    loss_mirror = None
    abandon_write = None
    if settings.archive.enabled:
        health = archive_health if archive_health is not None else ArchiveHealthSignals()
        archive_write = bind_archive_write(
            settings, db_manager, source, health, market_warm=market_warm
        )
        loss_mirror = bind_loss_mirror(db_manager, source)
        abandon_write = bind_abandon_write(db_manager, source, health)
    trade_poller = TradePoller(
        on_trade,
        redis=redis,
        settings=settings.polymarket,
        metadata=metadata_sync,
        on_state_change=on_ingestion_state,
        archive_write=archive_write,
        loss_mirror=loss_mirror,
        abandon_write=abandon_write,
    )

    return PipelineComponents(
        redis=redis,
        db_manager=db_manager,
        metadata_sync=metadata_sync,
        funding_tracer=funding_tracer,
        fresh_wallet_detector=fresh_detector,
        size_anomaly_detector=size_detector,
        detector_config=capture_detector_config(fresh_detector, size_detector),
        risk_scorer=risk_scorer,
        alert_formatter=alert_formatter,
        alert_dispatcher=alert_dispatcher,
        trade_poller=trade_poller,
    )


def publish_owed_metrics(
    health: ArchiveHealthSignals, metrics: PrometheusArchiveMetrics, now: float
) -> None:
    metrics.set_owed(health.owed_count(), health.oldest_owed_age(now))


def bind_archive_write(
    settings: Settings,
    db_manager: DatabaseManager,
    source: str,
    health: ArchiveHealthSignals,
    market_warm: MarketWarmCoordinator | None = None,
) -> Callable[[TradeObservation], Awaitable[bool]]:
    raw_retention = settings.archive.raw_retention
    metrics = PrometheusArchiveMetrics()

    async def archive_write(observation: TradeObservation) -> bool:
        now = time.time()
        health.mark_owed(observation.identity, now)
        ok = await persist_archive_observation(
            db_manager, source, raw_retention, metrics, observation
        )
        health.mark_attempt(now, failed=not ok)
        if ok:
            health.clear_owed(observation.identity)
            _schedule_market_warm(settings, db_manager, observation, market_warm)
            _schedule_featuring_enqueue(settings, db_manager, observation)
        else:
            metrics.record_write_failure("persist")
        publish_owed_metrics(health, metrics, now)
        return ok

    return archive_write


def _schedule_market_warm(
    settings: Settings,
    db_manager: DatabaseManager,
    observation: TradeObservation,
    market_warm: MarketWarmCoordinator | None,
) -> None:
    """Enqueue markets/knowability warm without awaiting (FR-002)."""
    from polymarket_insider_tracker.ingestor.archive.workers import schedule_market_warm

    schedule_market_warm(
        asyncio.get_running_loop(),
        db_manager,
        condition_id=observation.event.market_id,
        archive=settings.archive,
        coordinator=market_warm,
    )


def _schedule_featuring_enqueue(
    settings: Settings,
    db_manager: DatabaseManager,
    observation: TradeObservation,
) -> None:
    """Enqueue featuring evaluation without awaiting (FR-003)."""
    from polymarket_insider_tracker.ingestor.archive.featuring import schedule_featuring_enqueue

    schedule_featuring_enqueue(
        asyncio.get_running_loop(),
        db_manager,
        observation=observation,
        archive=settings.archive,
    )


async def persist_archive_observation(
    db_manager: DatabaseManager,
    source: str,
    raw_retention: bool,
    metrics: ArchiveMetrics,
    observation: TradeObservation,
) -> bool:
    async with db_manager.get_async_session() as session:
        writer = ArchiveWriter(
            session, source_id=source, raw_retention=raw_retention, metrics=metrics
        )
        result = await writer.write(observation)
        if result.status in {ArchiveWriteStatus.INSERTED, ArchiveWriteStatus.DUPLICATE}:
            await gap_ledger.resolve_write_failure(
                session, source_id=source, observation_id=observation.identity
            )
            return True
        await gap_ledger.record_write_failure(
            session,
            source_id=source,
            observation_id=observation.identity,
            detail={"status": result.status.value, "detail": result.detail},
        )
    return False


def bind_loss_mirror(
    db_manager: DatabaseManager, source: str
) -> Callable[[LossEvent], Awaitable[None]]:
    async def loss_mirror(event: LossEvent) -> None:
        async with db_manager.get_async_session() as session:
            await gap_ledger.mirror_loss_event(session, source_id=source, event=event)

    return loss_mirror


def bind_abandon_write(
    db_manager: DatabaseManager, source: str, health: ArchiveHealthSignals
) -> Callable[[TradeObservation], Awaitable[None]]:
    metrics = PrometheusArchiveMetrics()

    async def abandon_write(observation: TradeObservation) -> None:
        async with db_manager.get_async_session() as session:
            await gap_ledger.abandon_write_failure(
                session, source_id=source, observation_id=observation.identity
            )
        health.clear_owed(observation.identity)
        metrics.record_write_failure("abandoned")
        publish_owed_metrics(health, metrics, time.time())

    return abandon_write
