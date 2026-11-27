"""Configuration management service with Pydantic Settings.

This module provides centralized configuration management for the
Polymarket Insider Tracker application, loading and validating
environment variables at startup.
"""

from __future__ import annotations

import logging
import warnings
from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from polymarket_insider_tracker.archive_defaults import (
    DEFAULT_CLASSIFIER_CONTROL_SAMPLE_RATE,
    DEFAULT_ENRICHMENT_BUDGET_VERSION,
    DEFAULT_ENRICHMENT_HYDRATE_PAGES,
    DEFAULT_ENRICHMENT_HYDRATE_SECONDS,
    DEFAULT_ENRICHMENT_RPC_CAP,
    DEFAULT_ENRICHMENT_WALL_SECONDS,
    DEFAULT_FEATURE_VERSION,
    DEFAULT_FEATURING_CONFIG_VERSION,
    DEFAULT_FEATURING_NOTIONAL_CUTOFF_USDC,
    DEFAULT_FINGERPRINT_VERSION,
    DEFAULT_HOT_WINDOW_DAYS,
    DEFAULT_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY,
)
from polymarket_insider_tracker.deprecated_api_key import DeprecatedApiKey
from polymarket_insider_tracker.endpoints import OFFICIAL_V2_TRADES_URL, reject_v1_trades_url
from polymarket_insider_tracker.redaction import is_scannable_url_text, redact_url
from polymarket_insider_tracker.storage.database_url import normalize_database_url


def _check_url_scannable(value: str, name: str) -> None:
    """Reject raw characters the text-redaction scanner treats as URL boundaries.

    The central policy can only mask a credential-bearing endpoint inside
    diagnostic text while the whole URL stays one scan match; a raw
    whitespace, control, double-quote, or angle character would end the match
    early and let the tail — possibly a path credential — escape as prose.
    No such character is valid raw URI text, so rejection is fail-closed and
    lossless: percent-encoded forms remain accepted. The message never echoes
    the value.
    """
    if not is_scannable_url_text(value):
        raise ValueError(f"{name} contains raw whitespace, control, or quote/angle characters")


def _check_url_scheme(value: str, allowed_schemes: tuple[str, ...], name: str) -> None:
    expected_prefixes = tuple(f"{s}://" for s in allowed_schemes)
    if value.startswith(expected_prefixes):
        return
    if "ws" in allowed_schemes:
        raise ValueError(f"{name} must start with ws:// or wss://")
    raise ValueError(f"{name} must be an HTTP(S) endpoint")


def _check_nested_schemes(netloc: str, name: str) -> None:
    for s in ("http:", "https:", "ws:", "wss:"):
        if s in netloc:
            # Never echo the supplied URL: it may carry credentials (userinfo or query).
            raise ValueError(f"{name} contains a malformed nested scheme in its host component")


def _check_port(value: str, name: str) -> None:
    """Reject a URL whose port is non-numeric or out of range.

    The token after the host colon may itself be a credential (a mistyped
    ``host:key`` for ``host/key``); it must be rejected at validation so it
    never reaches config output, logs, or status, and the message keeps only
    the failure class, never the raw value. ``urlsplit().port`` attributes the
    colon correctly through userinfo and bracketed IPv6 hosts, so no netloc
    shape is exempt from the check.
    """
    try:
        _ = urlsplit(value).port
    except ValueError:
        raise ValueError(f"{name} has an invalid port") from None


def _check_url_components(value: str, allowed_schemes: tuple[str, ...], name: str) -> str:
    _check_url_scannable(value, name)
    _check_url_scheme(value, allowed_schemes, name)
    parts = urlsplit(value)
    if not parts.hostname:
        raise ValueError(f"{name} must include a valid hostname")
    _check_port(value, name)
    _check_nested_schemes(parts.netloc, name)
    return value


def _validate_redis_url(value: str) -> str:
    """Validate Redis URL format."""
    _check_url_scannable(value, "REDIS_URL")
    if not value.startswith("redis://"):
        raise ValueError("REDIS_URL must start with redis://")
    parts = urlsplit(value)
    if not parts.hostname:
        raise ValueError("REDIS_URL must include a valid hostname")
    _check_port(value, "REDIS_URL")
    return value


def _validate_http_url(value: str) -> str:
    """Validate RPC URL format."""
    return _check_url_components(value, ("http", "https"), "RPC URL")


def _validate_websocket_url(value: str) -> str:
    """Validate WebSocket URL format."""
    return _check_url_components(value, ("ws", "wss"), "WebSocket URL")


def _validate_webhook_url_secret(value: SecretStr) -> SecretStr:
    """An enabled webhook URL must satisfy the same scannability invariant.

    A blank value means the channel is disabled and stays accepted. The
    check never echoes the secret value.
    """
    secret = value.get_secret_value()
    if secret.strip():
        _check_url_scannable(secret, "DISCORD_WEBHOOK_URL")
    return value


# Field-level validation is attached through annotated types so each rule is an ordinary function
# whose use is visible to readers and static tooling alike.
CanonicalDatabaseUrl = Annotated[str, AfterValidator(normalize_database_url)]
RedisUrl = Annotated[str, AfterValidator(_validate_redis_url)]
HttpEndpointUrl = Annotated[str, AfterValidator(_validate_http_url)]
WebSocketEndpointUrl = Annotated[str, AfterValidator(_validate_websocket_url)]
DiscordWebhookUrl = Annotated[SecretStr, AfterValidator(_validate_webhook_url_secret)]


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    url: CanonicalDatabaseUrl = Field(
        alias="DATABASE_URL",
        description="PostgreSQL connection string",
    )

    if TYPE_CHECKING:
        # BaseSettings resolves the required URL from DATABASE_URL, which the checkers'
        # synthesized constructor (one required alias argument) cannot express.
        def __init__(self) -> None: ...


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    url: RedisUrl = Field(
        default="redis://localhost:6379",
        alias="REDIS_URL",
        description="Redis connection string",
    )


class PolygonSettings(BaseSettings):
    """Polygon blockchain RPC settings."""

    model_config = SettingsConfigDict(
        env_prefix="POLYGON_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    rpc_url: HttpEndpointUrl = Field(
        default="https://polygon-rpc.com",
        alias="POLYGON_RPC_URL",
        description="Primary Polygon RPC endpoint",
    )
    fallback_rpc_url: HttpEndpointUrl | None = Field(
        default=None,
        alias="POLYGON_FALLBACK_RPC_URL",
        description="Fallback Polygon RPC endpoint",
    )


class TradesCoverage(StrEnum):
    """Which public participant observations the trades query returns."""

    ALL = "all"
    TAKER_ONLY = "taker-only"


class WebSocketSettingDeprecationWarning(UserWarning):
    """``POLYMARKET_WS_URL`` is deprecated and never used for acquisition."""


TRADES_REPLACEMENT_VARIABLES = (
    "POLYMARKET_TRADES_URL",
    "POLYMARKET_TRADES_COVERAGE",
    "POLYMARKET_TRADES_POLL_INTERVAL_SECONDS",
    "POLYMARKET_TRADES_RECOVERY_HORIZON_SECONDS",
)


def websocket_deprecation_message() -> str:
    """The actionable, value-free text emitted when the legacy WebSocket setting is set."""
    return (
        "POLYMARKET_WS_URL is deprecated and not used for trade acquisition; the tracker polls "
        "the documented public trades query. Remove it and configure "
        + ", ".join(TRADES_REPLACEMENT_VARIABLES)
        + " instead."
    )


def _warn_about_deprecated_websocket_url(value: str) -> str:
    """Accept a legacy WebSocket URL with the deprecation warning; the value is never printed."""
    warnings.warn(websocket_deprecation_message(), WebSocketSettingDeprecationWarning, stacklevel=2)
    return value


DeprecatedWebSocketUrl = Annotated[
    WebSocketEndpointUrl, AfterValidator(_warn_about_deprecated_websocket_url)
]


class PolymarketSettings(BaseSettings):
    """Polymarket public data source settings."""

    model_config = SettingsConfigDict(
        env_prefix="POLYMARKET_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    trades_url: Annotated[HttpEndpointUrl, AfterValidator(reject_v1_trades_url)] = Field(
        default=OFFICIAL_V2_TRADES_URL,
        alias="POLYMARKET_TRADES_URL",
        description="Documented anonymous public trades query (official v2; v1 retired 2026-10-24)",
    )
    trades_coverage: TradesCoverage = Field(
        default=TradesCoverage.ALL,
        alias="POLYMARKET_TRADES_COVERAGE",
        description="all participant observations (default) or the provider's taker-only subset",
    )
    trades_poll_interval_seconds: int = Field(
        default=5,
        alias="POLYMARKET_TRADES_POLL_INTERVAL_SECONDS",
        description="Seconds between acquisition cycles; 1 keeps the budget at 5% of the limit",
        ge=1,
        le=60,
    )
    trades_recovery_horizon_seconds: int = Field(
        default=600,
        alias="POLYMARKET_TRADES_RECOVERY_HORIZON_SECONDS",
        description="Identity retention and loss-detection horizon; not a completeness guarantee",
        ge=60,
        le=3600,
    )
    ws_url: DeprecatedWebSocketUrl | None = Field(
        default=None,
        alias="POLYMARKET_WS_URL",
        description="Deprecated legacy WebSocket URL; accepted with a warning and never used",
    )
    api_key: DeprecatedApiKey | None = Field(
        default=None, alias="POLYMARKET_API_KEY", description="Deprecated; ignored"
    )

    @property
    def ws_url_disposition(self) -> str:
        """Render the legacy setting's state without its value."""
        return "(deprecated, set)" if self.ws_url is not None else "(not set)"


class DiscordSettings(BaseSettings):
    """Discord notification settings."""

    model_config = SettingsConfigDict(
        env_prefix="DISCORD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    webhook_url: DiscordWebhookUrl | None = Field(
        default=None,
        alias="DISCORD_WEBHOOK_URL",
        description="Discord webhook URL for alerts",
    )

    @property
    def enabled(self) -> bool:
        """Check if Discord notifications are enabled."""
        return self.webhook_url is not None and bool(self.webhook_url.get_secret_value().strip())


class TelegramSettings(BaseSettings):
    """Telegram notification settings."""

    model_config = SettingsConfigDict(
        env_prefix="TELEGRAM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    bot_token: SecretStr | None = Field(
        default=None,
        alias="TELEGRAM_BOT_TOKEN",
        description="Telegram bot token",
    )
    chat_id: str | None = Field(
        default=None,
        alias="TELEGRAM_CHAT_ID",
        description="Telegram chat ID for alerts",
    )

    @property
    def enabled(self) -> bool:
        """Check if Telegram notifications are enabled."""
        return (
            self.bot_token is not None
            and bool(self.bot_token.get_secret_value().strip())
            and self.chat_id is not None
            and bool(self.chat_id.strip())
        )


class DetectorSettings(BaseSettings):
    """Risk-scorer / detector tuning."""

    model_config = SettingsConfigDict(
        env_prefix="DETECTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    alert_threshold: float = Field(
        default=0.80,
        alias="DETECTOR_ALERT_THRESHOLD",
        description="Minimum weighted score required to trigger an alert",
        ge=0.0,
        le=1.0,
    )
    dedup_window_seconds: int = Field(
        default=3600,
        alias="DETECTOR_DEDUP_WINDOW_SECONDS",
        description="Per-(wallet, market) dedup window in seconds",
        ge=0,
    )
    persist_assessments: bool = Field(
        default=True,
        alias="DETECTOR_PERSIST_ASSESSMENTS",
        description="Write every signal-bearing risk assessment to the database",
    )


class ArchiveSettings(BaseSettings):
    """Opt-in research trades-tape writing plus markets/knowability/repair flags."""

    model_config = SettingsConfigDict(
        env_prefix="ARCHIVE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    enabled: bool = Field(
        default=False,
        alias="ARCHIVE_ENABLED",
        description="Persist admitted fills to the research trades tape (default off)",
    )
    raw_retention: bool = Field(
        default=True,
        alias="ARCHIVE_RAW_RETENTION",
        description="Store Core hot raw_row_json when archive writing is enabled",
    )
    outcome_repair_enabled: bool = Field(
        default=False,
        alias="ARCHIVE_OUTCOME_REPAIR_ENABLED",
        description="Async forward-only outcome repair (requires ARCHIVE_ENABLED; default off)",
    )
    outcome_repair_lag_seconds: int = Field(
        default=300,
        alias="ARCHIVE_OUTCOME_REPAIR_LAG_SECONDS",
        description="Post-cutover thin rows still not_attempted after this lag trip KPI",
        ge=0,
    )
    outcome_repair_unrepaired_max_ratio: float = Field(
        default=0.05,
        alias="ARCHIVE_OUTCOME_REPAIR_UNREPAIRED_MAX_RATIO",
        description="Ceiling unrepaired share among thin post-cutover rows (trailing day)",
        ge=0.0,
        le=1.0,
    )
    knowability_model_enabled: bool = Field(
        default=True,
        alias="ARCHIVE_KNOWABILITY_MODEL_ENABLED",
        description="Model-on-miss intent; false forces off; effective on needs credentials",
    )
    knowability_model_max_calls_per_day: int = Field(
        default=DEFAULT_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY,
        alias="ARCHIVE_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY",
        description="Hard UTC-day ceiling for Decisions API knowability calls",
        ge=0,
    )
    knowability_model_api_key: SecretStr | None = Field(
        default=None,
        alias="ARCHIVE_KNOWABILITY_MODEL_API_KEY",
        description="OpenAI Decisions API key (secret); absent → model effectively off",
    )
    featuring_enabled: bool = Field(
        default=False,
        alias="ARCHIVE_FEATURING_ENABLED",
        description="Async featuring/enrichment workers (requires ARCHIVE_ENABLED; default off)",
    )
    featuring_config_version: str = Field(
        default=DEFAULT_FEATURING_CONFIG_VERSION,
        alias="ARCHIVE_FEATURING_CONFIG_VERSION",
        description="Version stamp for featuring gate + cutoff policy",
    )
    featuring_notional_cutoff_usdc: int = Field(
        default=DEFAULT_FEATURING_NOTIONAL_CUTOFF_USDC,
        alias="ARCHIVE_FEATURING_NOTIONAL_CUTOFF_USDC",
        description="Provisional notional gate in USDC (versioned with featuring_config_version)",
        ge=0,
    )
    featuring_unknown_opt_in: bool = Field(
        default=False,
        alias="ARCHIVE_FEATURING_UNKNOWN_OPT_IN",
        description="Opt unknown regime into featuring only via explicit versioned bump",
    )
    classifier_control_sample_rate: float = Field(
        default=DEFAULT_CLASSIFIER_CONTROL_SAMPLE_RATE,
        alias="ARCHIVE_CLASSIFIER_CONTROL_SAMPLE_RATE",
        description="Seeded sample rate of featuring-rejected no_private_edge fills",
        ge=0.0,
        le=1.0,
    )
    enrichment_budget_version: str = Field(
        default=DEFAULT_ENRICHMENT_BUDGET_VERSION,
        alias="ARCHIVE_ENRICHMENT_BUDGET_VERSION",
        description="Version stamp for enrichment wall/RPC/hydrate caps",
    )
    enrichment_wall_seconds: int = Field(
        default=DEFAULT_ENRICHMENT_WALL_SECONDS,
        alias="ARCHIVE_ENRICHMENT_WALL_SECONDS",
        description="Provisional wall-clock budget per enrichment attempt",
        ge=1,
    )
    enrichment_rpc_cap: int = Field(
        default=DEFAULT_ENRICHMENT_RPC_CAP,
        alias="ARCHIVE_ENRICHMENT_RPC_CAP",
        description="Provisional Polygon RPC call budget per featured attempt",
        ge=0,
    )
    enrichment_hydrate_pages: int = Field(
        default=DEFAULT_ENRICHMENT_HYDRATE_PAGES,
        alias="ARCHIVE_ENRICHMENT_HYDRATE_PAGES",
        description="Provisional Data API page cap for lifetime hydrate",
        ge=0,
    )
    enrichment_hydrate_seconds: int = Field(
        default=DEFAULT_ENRICHMENT_HYDRATE_SECONDS,
        alias="ARCHIVE_ENRICHMENT_HYDRATE_SECONDS",
        description="Provisional wall budget for lifetime hydrate arm",
        ge=1,
    )
    fingerprint_version: str = Field(
        default=DEFAULT_FINGERPRINT_VERSION,
        alias="ARCHIVE_FINGERPRINT_VERSION",
        description="Version stamp for strong vs weak fill fingerprint rules",
    )
    feature_version: str = Field(
        default=DEFAULT_FEATURE_VERSION,
        alias="ARCHIVE_FEATURE_VERSION",
        description="Version stamp for optional trade_features snapshots",
    )
    hot_window_days: int = Field(
        default=DEFAULT_HOT_WINDOW_DAYS,
        alias="ARCHIVE_HOT_WINDOW_DAYS",
        description="Hot retention window used for featured backfill eligibility (7–30)",
        ge=7,
        le=30,
    )
    collect_priority: bool = Field(
        default=False,
        alias="ARCHIVE_COLLECT_PRIORITY",
        description=(
            "When archive is on, skip size-anomaly CLOB lookups on the trade hot path "
            "so acquisition is not starved during tape burn-in"
        ),
    )

    @property
    def knowability_model_credentials_present(self) -> bool:
        key = self.knowability_model_api_key
        return key is not None and bool(key.get_secret_value().strip())

    @property
    def knowability_model_effectively_enabled(self) -> bool:
        return self.knowability_model_enabled and self.knowability_model_credentials_present

    @property
    def outcome_repair_effectively_enabled(self) -> bool:
        return self.enabled and self.outcome_repair_enabled

    @property
    def featuring_effectively_enabled(self) -> bool:
        return self.enabled and self.featuring_enabled

    @property
    def collect_priority_effectively_enabled(self) -> bool:
        return self.enabled and self.collect_priority


class Settings(BaseSettings):
    """Main application settings.

    Loads configuration from environment variables with support for
    .env files via python-dotenv.

    Example:
        ```python
        from polymarket_insider_tracker.config import get_settings

        settings = get_settings()
        print(settings.database.url)
        print(settings.log_level)
        ```
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Nested configuration groups
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    polygon: PolygonSettings = Field(default_factory=PolygonSettings)
    polymarket: PolymarketSettings = Field(default_factory=PolymarketSettings)
    discord: DiscordSettings = Field(default_factory=DiscordSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    detector: DetectorSettings = Field(default_factory=DetectorSettings)
    archive: ArchiveSettings = Field(default_factory=ArchiveSettings)

    # Application settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Logging level",
    )
    health_port: int = Field(
        default=8080,
        alias="HEALTH_PORT",
        description="HTTP port for health check endpoints",
        ge=1,
        le=65535,
    )
    dry_run: bool = Field(
        default=False,
        alias="DRY_RUN",
        description="Run without sending actual alerts",
    )

    def get_logging_level(self) -> int:
        """Get the numeric logging level."""
        level: int = getattr(logging, self.log_level)
        return level

    def redacted_summary(self) -> dict[str, str | dict[str, str]]:
        """Get a summary of settings with secrets redacted.

        Returns:
            Dictionary of settings with sensitive values masked.
        """
        polygon_fallback = self.polygon.fallback_rpc_url
        return {
            "database_url": self._redact_url(self.database.url),
            "redis_url": self._redact_url(self.redis.url),
            "polygon": {
                "rpc_url": self._redact_url(self.polygon.rpc_url),
                "fallback_rpc_url": (
                    self._redact_url(polygon_fallback) if polygon_fallback else "(not set)"
                ),
            },
            "polymarket": {
                "trades_url": self._redact_url(self.polymarket.trades_url),
                "coverage": self.polymarket.trades_coverage.value,
                "poll_interval_seconds": str(self.polymarket.trades_poll_interval_seconds),
                "recovery_horizon_seconds": str(self.polymarket.trades_recovery_horizon_seconds),
                "ws_url": self.polymarket.ws_url_disposition,
                "api_key": "(set)" if self.polymarket.api_key else "(not set)",
            },
            "discord_enabled": str(self.discord.enabled),
            "telegram_enabled": str(self.telegram.enabled),
            "log_level": self.log_level,
            "health_port": str(self.health_port),
            "dry_run": str(self.dry_run),
            "archive": self._archive_redacted_summary(),
        }

    def _archive_redacted_summary(self) -> dict[str, str]:
        archive = self.archive
        return {
            "enabled": str(archive.enabled),
            "raw_retention": str(archive.raw_retention),
            "outcome_repair_enabled": str(archive.outcome_repair_enabled),
            "outcome_repair_lag_seconds": str(archive.outcome_repair_lag_seconds),
            "outcome_repair_unrepaired_max_ratio": str(archive.outcome_repair_unrepaired_max_ratio),
            "knowability_model_enabled": str(archive.knowability_model_enabled),
            "knowability_model_max_calls_per_day": str(archive.knowability_model_max_calls_per_day),
            "knowability_model_api_key": (
                "(set)" if archive.knowability_model_credentials_present else "(not set)"
            ),
            "featuring_enabled": str(archive.featuring_enabled),
            "featuring_config_version": archive.featuring_config_version,
            "featuring_notional_cutoff_usdc": str(archive.featuring_notional_cutoff_usdc),
            "featuring_unknown_opt_in": str(archive.featuring_unknown_opt_in),
            "classifier_control_sample_rate": str(archive.classifier_control_sample_rate),
            "enrichment_budget_version": archive.enrichment_budget_version,
            "enrichment_wall_seconds": str(archive.enrichment_wall_seconds),
            "enrichment_rpc_cap": str(archive.enrichment_rpc_cap),
            "enrichment_hydrate_pages": str(archive.enrichment_hydrate_pages),
            "enrichment_hydrate_seconds": str(archive.enrichment_hydrate_seconds),
            "fingerprint_version": archive.fingerprint_version,
            "feature_version": archive.feature_version,
            "hot_window_days": str(archive.hot_window_days),
            "collect_priority": str(archive.collect_priority),
        }

    @staticmethod
    def _redact_url(url: str) -> str:
        """Mask userinfo and query-string credentials via the central redaction helper."""
        return redact_url(url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get the application settings singleton.

    Uses LRU cache to ensure settings are loaded only once and
    reused across the application.

    Returns:
        The Settings instance.

    Raises:
        ValidationError: If required environment variables are missing
            or have invalid values.
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache.

    Useful for testing when you need to reload settings with
    different environment variables.
    """
    get_settings.cache_clear()
