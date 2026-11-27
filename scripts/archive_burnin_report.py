#!/usr/bin/env python3
"""Fixed post-run archive burn-in analysis pack (early $500 / production $5k lenses)."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from polymarket_insider_tracker.config import get_settings

EARLY_CUTOFF = 500.0
PROD_CUTOFF = 5000.0
GALLERY_LIMIT = 5

TRADE_CATEGORICAL: tuple[str, ...] = (
    "side",
    "source",
    "outcome_repair_status",
    "receipt_status",
    "gamma_enrichment_status",
    "funding_lookup_status",
    "wallet_hydrate_status",
    "featuring_reason",
    "info_knowability_regime",
    "knowability_label_source",
    "fingerprint_version",
    "featuring_config_version",
    "enrichment_budget_version",
)

TRADE_PRESENCE: tuple[str, ...] = (
    "raw_row_json",
    "fill_fingerprint",
    "outcome",
    "block_number",
    "log_index",
    "onchain_direction",
    "fee_usdc",
    "counterparty_wallets",
)

MARKET_CATEGORICAL: tuple[str, ...] = (
    "knowability_policy_version",
    "info_knowability_regime",
    "knowability_label_source",
    "source_version",
)

ALLOWED: dict[str, frozenset[str]] = {
    "side": frozenset({"BUY", "SELL"}),
    "source": frozenset({"data-api.trades"}),
    "outcome_repair_status": frozenset({"not_attempted", "not_needed", "ok", "unrepaired"}),
    "receipt_status": frozenset(
        {"not_attempted", "pending", "ok", "partial", "failed", "skipped_budget"}
    ),
    "gamma_enrichment_status": frozenset(
        {"not_attempted", "pending", "ok", "partial", "failed", "skipped_budget"}
    ),
    "funding_lookup_status": frozenset(
        {"not_attempted", "pending", "ok", "partial", "failed", "skipped_budget"}
    ),
    "wallet_hydrate_status": frozenset(
        {"not_attempted", "pending", "ok", "partial", "failed", "skipped_budget"}
    ),
    "featuring_reason": frozenset(
        {
            "featuring_disabled",
            "regime_no_private_edge",
            "regime_unknown",
            "below_notional",
            "eligible",
            "classifier_control",
        }
    ),
    "info_knowability_regime": frozenset(
        {
            "no_private_edge",
            "private_settlement_possible",
            "private_factor_possible",
            "private_edge_possible",
            "unknown",
        }
    ),
    "knowability_label_source": frozenset(
        {
            "unknown",
            "override",
            "series",
            "question",
            "template",
            "title_rule",
            "model",
        }
    ),
    "fingerprint_version": frozenset({"b.v2"}),
    "featuring_config_version": frozenset({"b.v1"}),
    "enrichment_budget_version": frozenset({"b.v1"}),
    "knowability_policy_version": frozenset({"knowability.v5", "knowability.v4", "knowability.v3"}),
    "source_version": frozenset({"gamma"}),
}


def _parse_mark(raw: str) -> datetime:
    text_value = raw.strip()
    if text_value.endswith("Z"):
        text_value = f"{text_value[:-1]}+00:00"
    return datetime.fromisoformat(text_value).astimezone(UTC)


def _load_mark(raw: str) -> datetime:
    for line in raw.splitlines():
        text_value = line.strip()
        if not text_value or text_value.startswith("#"):
            continue
        if text_value.startswith("RUN_MARK="):
            return _parse_mark(text_value.split("=", 1)[1])
        if "=" not in text_value:
            return _parse_mark(text_value)
    return _parse_mark(raw)


def _engine() -> Engine:
    return create_engine(get_settings().database.url, future=True)


def _scalar(conn: Connection, sql: str, params: Mapping[str, Any]) -> Any:
    return conn.execute(text(sql), dict(params)).scalar()


def _rows(conn: Connection, sql: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text(sql), dict(params)).mappings()]


def _pct(part: int | float | None, whole: int | float | None) -> float | None:
    if part is None or whole is None or whole <= 0:
        return None
    return round(100.0 * float(part) / float(whole), 2)


def _bucket_map(rows: Sequence[Mapping[str, Any]], key: str = "value") -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        label = row.get(key)
        out[str(label) if label is not None else "null"] = int(row["n"])
    return out


def _unexpected(field: str, buckets: Mapping[str, int]) -> list[str]:
    allowed = ALLOWED.get(field)
    if allowed is None:
        return []
    bad: list[str] = []
    for value, count in buckets.items():
        if value == "null" or count <= 0:
            continue
        if value not in allowed:
            bad.append(f"{field}={value}({count})")
    return bad


def _window_params(
    mark: datetime,
    ended: datetime,
    *,
    min_notional: float | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"mark": mark, "ended": ended}
    if min_notional is not None:
        params["min_notional"] = min_notional
    return params


def _trade_filters(
    *,
    min_notional: float | None,
    completed_only: bool,
) -> tuple[str, str]:
    where = ["t.observed_at >= :mark", "t.observed_at < :ended"]
    joins = ""
    if min_notional is not None:
        where.append("t.notional_usdc >= :min_notional")
    if completed_only:
        joins = (
            " JOIN enrichment_work_items w"
            " ON w.observation_id = t.observation_id"
            " AND w.trade_ts = t.trade_ts"
            " AND w.status = 'completed'"
        )
    return joins, " AND ".join(where)


def _trade_breakdown(
    conn: Connection,
    column: str,
    mark: datetime,
    ended: datetime,
    *,
    min_notional: float | None = None,
    completed_only: bool = False,
) -> dict[str, int]:
    if column not in TRADE_CATEGORICAL:
        raise ValueError(f"unknown categorical column: {column}")
    joins, where_sql = _trade_filters(min_notional=min_notional, completed_only=completed_only)
    sql = (
        f"SELECT t.{column} AS value, COUNT(*) AS n FROM trades t{joins}"
        f" WHERE {where_sql} GROUP BY 1 ORDER BY n DESC"
    )
    return _bucket_map(_rows(conn, sql, _window_params(mark, ended, min_notional=min_notional)))


def _trade_presence(
    conn: Connection,
    column: str,
    mark: datetime,
    ended: datetime,
    *,
    min_notional: float | None = None,
    completed_only: bool = False,
) -> dict[str, int]:
    if column not in TRADE_PRESENCE and column != "neg_risk":
        raise ValueError(f"unknown presence column: {column}")
    joins, where_sql = _trade_filters(min_notional=min_notional, completed_only=completed_only)
    params = _window_params(mark, ended, min_notional=min_notional)
    if column == "neg_risk":
        sql = (
            f"SELECT CASE WHEN t.neg_risk IS NULL THEN 'null'"
            f" WHEN t.neg_risk THEN 'true' ELSE 'false' END AS value,"
            f" COUNT(*) AS n FROM trades t{joins}"
            f" WHERE {where_sql} GROUP BY 1 ORDER BY n DESC"
        )
        return _bucket_map(_rows(conn, sql, params))
    sql = (
        f"SELECT CASE WHEN t.{column} IS NULL THEN 'null' ELSE 'present' END AS value,"
        f" COUNT(*) AS n FROM trades t{joins}"
        f" WHERE {where_sql} GROUP BY 1 ORDER BY n DESC"
    )
    return _bucket_map(_rows(conn, sql, params))


def _all_trade_fields(
    conn: Connection,
    mark: datetime,
    ended: datetime,
    *,
    min_notional: float | None = None,
    completed_only: bool = False,
) -> dict[str, Any]:
    categorical = {
        col: _trade_breakdown(
            conn,
            col,
            mark,
            ended,
            min_notional=min_notional,
            completed_only=completed_only,
        )
        for col in TRADE_CATEGORICAL
    }
    presence = {
        col: _trade_presence(
            conn,
            col,
            mark,
            ended,
            min_notional=min_notional,
            completed_only=completed_only,
        )
        for col in (*TRADE_PRESENCE, "neg_risk")
    }
    unexpected: list[str] = []
    for col, buckets in categorical.items():
        unexpected.extend(_unexpected(col, buckets))
    return {
        "categorical": categorical,
        "presence": presence,
        "unexpected_values": unexpected,
    }


def _market_breakdown(
    conn: Connection, column: str, mark: datetime, ended: datetime
) -> dict[str, int]:
    if column not in MARKET_CATEGORICAL:
        raise ValueError(f"unknown market column: {column}")
    sql = (
        f"SELECT {column} AS value, COUNT(*) AS n FROM markets"
        f" WHERE known_at >= :mark AND known_at < :ended"
        f" GROUP BY 1 ORDER BY n DESC"
    )
    return _bucket_map(_rows(conn, sql, {"mark": mark, "ended": ended}))


def _acquisition(conn: Connection, mark: datetime, ended: datetime) -> dict[str, Any]:
    inserts = int(
        _scalar(
            conn,
            "SELECT COUNT(*) FROM trades WHERE observed_at >= :mark AND observed_at < :ended",
            {"mark": mark, "ended": ended},
        )
        or 0
    )
    span_s = max((ended - mark).total_seconds(), 1.0)
    lag = _rows(
        conn,
        """
        SELECT
          percentile_cont(0.5) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (observed_at - trade_ts))
          ) AS p50,
          percentile_cont(0.95) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (observed_at - trade_ts))
          ) AS p95
        FROM trades
        WHERE observed_at >= :mark AND observed_at < :ended
        """,
        {"mark": mark, "ended": ended},
    )[0]
    gaps = _rows(
        conn,
        """
        SELECT class AS gap_class, reason, COUNT(*) AS n
        FROM ingest_gap_events
        WHERE detected_at >= :mark AND detected_at < :ended
        GROUP BY 1, 2 ORDER BY n DESC
        """,
        {"mark": mark, "ended": ended},
    )
    return {
        "inserts": inserts,
        "inserts_per_min": round(inserts / (span_s / 60.0), 2),
        "lag_seconds": {
            "p50": None if lag["p50"] is None else round(float(lag["p50"]), 3),
            "p95": None if lag["p95"] is None else round(float(lag["p95"]), 3),
        },
        "gaps_by_class_reason": [
            {
                "gap_class": g["gap_class"],
                "reason": g["reason"],
                "n": int(g["n"]),
            }
            for g in gaps
        ],
    }


def _queue(conn: Connection, mark: datetime, ended: datetime) -> dict[str, Any]:
    by_trigger = _rows(
        conn,
        """
        SELECT trigger, status, COUNT(*) AS n
        FROM enrichment_work_items
        WHERE enqueued_at >= :mark AND enqueued_at < :ended
        GROUP BY 1, 2 ORDER BY 1, 2
        """,
        {"mark": mark, "ended": ended},
    )
    reason = _trade_breakdown(conn, "featuring_reason", mark, ended)
    first_unknown = int(
        _scalar(
            conn,
            """
            SELECT COUNT(*) FROM trades t
            WHERE t.observed_at >= :mark AND t.observed_at < :ended
              AND t.info_knowability_regime = 'unknown'
              AND NOT EXISTS (
                SELECT 1 FROM trades prior
                WHERE prior.condition_id = t.condition_id
                  AND prior.observed_at < t.observed_at
              )
            """,
            {"mark": mark, "ended": ended},
        )
        or 0
    )
    later_unknown = int(
        _scalar(
            conn,
            """
            SELECT COUNT(*) FROM trades t
            WHERE t.observed_at >= :mark AND t.observed_at < :ended
              AND t.info_knowability_regime = 'unknown'
              AND EXISTS (
                SELECT 1 FROM trades prior
                WHERE prior.condition_id = t.condition_id
                  AND prior.observed_at < t.observed_at
              )
            """,
            {"mark": mark, "ended": ended},
        )
        or 0
    )
    return {
        "work_items_by_trigger_status": [
            {"trigger": r["trigger"], "status": r["status"], "n": int(r["n"])} for r in by_trigger
        ],
        "featuring_reason": reason,
        "unknown_first_seen_condition": first_unknown,
        "unknown_later_repeat": later_unknown,
    }


def _markets_pack(conn: Connection, mark: datetime, ended: datetime) -> dict[str, Any]:
    categorical = {col: _market_breakdown(conn, col, mark, ended) for col in MARKET_CATEGORICAL}
    unexpected: list[str] = []
    for col, buckets in categorical.items():
        unexpected.extend(_unexpected(col, buckets))
    total = int(
        _scalar(
            conn,
            "SELECT COUNT(*) FROM markets WHERE known_at >= :mark AND known_at < :ended",
            {"mark": mark, "ended": ended},
        )
        or 0
    )
    return {
        "categorical": categorical,
        "unexpected_values": unexpected,
        "rows_in_window": total,
    }


def _cohort_count(
    conn: Connection,
    mark: datetime,
    ended: datetime,
    *,
    min_notional: float,
) -> int:
    return int(
        _scalar(
            conn,
            """
            SELECT COUNT(*) FROM trades
            WHERE observed_at >= :mark AND observed_at < :ended
              AND notional_usdc >= :min_notional
            """,
            {"mark": mark, "ended": ended, "min_notional": min_notional},
        )
        or 0
    )


def _completed_arm_mix(
    conn: Connection,
    mark: datetime,
    ended: datetime,
    *,
    min_notional: float | None = None,
) -> dict[str, Any]:
    where = [
        "w.status = 'completed'",
        "w.finished_at >= :mark",
        "w.finished_at < :ended",
    ]
    params: dict[str, Any] = {"mark": mark, "ended": ended}
    if min_notional is not None:
        where.append("t.notional_usdc >= :min_notional")
        params["min_notional"] = min_notional
    sql = f"""
        SELECT
          COUNT(*) AS completed,
          COUNT(*) FILTER (WHERE t.gamma_enrichment_status = 'ok') AS gamma_ok,
          COUNT(*) FILTER (WHERE t.gamma_enrichment_status = 'partial') AS gamma_partial,
          COUNT(*) FILTER (WHERE t.receipt_status = 'pending') AS receipt_pending,
          COUNT(*) FILTER (WHERE t.funding_lookup_status = 'pending') AS funding_pending,
          COUNT(*) FILTER (WHERE t.wallet_hydrate_status = 'pending') AS hydrate_pending,
          COUNT(*) FILTER (
            WHERE t.gamma_enrichment_status = 'partial'
              AND t.receipt_status = 'pending'
              AND t.funding_lookup_status = 'pending'
              AND t.wallet_hydrate_status = 'pending'
          ) AS expected_partial_stub_mix
        FROM enrichment_work_items w
        JOIN trades t
          ON t.observation_id = w.observation_id AND t.trade_ts = w.trade_ts
        WHERE {' AND '.join(where)}
    """
    row = _rows(conn, sql, params)[0]
    completed = int(row["completed"] or 0)
    return {
        "completed": completed,
        "gamma_ok": int(row["gamma_ok"] or 0),
        "gamma_partial": int(row["gamma_partial"] or 0),
        "receipt_pending": int(row["receipt_pending"] or 0),
        "funding_pending": int(row["funding_pending"] or 0),
        "hydrate_pending": int(row["hydrate_pending"] or 0),
        "expected_partial_stub_mix": int(row["expected_partial_stub_mix"] or 0),
        "pct_expected_partial_stub_mix": _pct(
            int(row["expected_partial_stub_mix"] or 0), completed
        ),
    }


def _price_size_sanity(conn: Connection, mark: datetime, ended: datetime) -> dict[str, int]:
    row = _rows(
        conn,
        """
        SELECT
          COUNT(*) FILTER (WHERE price < 0 OR price > 1) AS price_out_of_unit,
          COUNT(*) FILTER (WHERE size_shares <= 0) AS nonpositive_size,
          COUNT(*) FILTER (WHERE notional_usdc < 0) AS negative_notional,
          COUNT(*) AS n
        FROM trades
        WHERE observed_at >= :mark AND observed_at < :ended
        """,
        {"mark": mark, "ended": ended},
    )[0]
    return {k: int(row[k] or 0) for k in row}


def _gallery(conn: Connection, mark: datetime, ended: datetime) -> list[dict[str, Any]]:
    picks = _rows(
        conn,
        """
        WITH ranked AS (
          SELECT t.observation_id, t.trade_ts,
            CASE
              WHEN t.notional_usdc >= :prod THEN 1
              WHEN t.notional_usdc >= :early
                   AND t.info_knowability_regime = 'unknown' THEN 2
              WHEN w.trigger = 'insert_time' AND w.status = 'completed' THEN 3
              WHEN t.info_knowability_regime IN (
                'no_private_edge',
                'private_settlement_possible',
                'private_factor_possible',
                'private_edge_possible'
              ) THEN 4
              ELSE 5
            END AS bucket
          FROM trades t
          LEFT JOIN enrichment_work_items w
            ON w.observation_id = t.observation_id AND w.trade_ts = t.trade_ts
          WHERE t.observed_at >= :mark AND t.observed_at < :ended
        ),
        chosen AS (
          SELECT DISTINCT ON (bucket) observation_id, trade_ts, bucket
          FROM ranked ORDER BY bucket, observation_id, trade_ts
          LIMIT :lim
        )
        SELECT observation_id, trade_ts FROM chosen ORDER BY bucket
        """,
        {
            "mark": mark,
            "ended": ended,
            "early": EARLY_CUTOFF,
            "prod": PROD_CUTOFF,
            "lim": GALLERY_LIMIT,
        },
    )
    out: list[dict[str, Any]] = []
    for pick in picks:
        out.append(_gallery_bundle(conn, pick["observation_id"], pick["trade_ts"]))
    return out


def _gallery_bundle(conn: Connection, observation_id: str, trade_ts: datetime) -> dict[str, Any]:
    trade = _rows(
        conn,
        """
        SELECT * FROM trades
        WHERE observation_id = :id AND trade_ts = :ts
        """,
        {"id": observation_id, "ts": trade_ts},
    )[0]
    work = _rows(
        conn,
        """
        SELECT * FROM enrichment_work_items
        WHERE observation_id = :id AND trade_ts = :ts
        """,
        {"id": observation_id, "ts": trade_ts},
    )
    market = _rows(
        conn,
        """
        SELECT * FROM markets
        WHERE condition_id = :cid
          AND known_at <= :ts
          AND knowability_policy_version IN ('knowability.v4', 'knowability.v3')
        ORDER BY known_at DESC LIMIT 1
        """,
        {"cid": trade["condition_id"], "ts": trade["trade_ts"]},
    )
    wallet = _rows(
        conn,
        """
        SELECT * FROM wallets WHERE proxy_wallet = :w
        ORDER BY known_at DESC LIMIT 1
        """,
        {"w": trade["proxy_wallet"]},
    )
    funding = _rows(
        conn,
        """
        SELECT * FROM proxy_funding WHERE proxy_wallet = :w
        ORDER BY known_at DESC LIMIT 5
        """,
        {"w": trade["proxy_wallet"]},
    )
    return {
        "observation_id": observation_id,
        "trade_ts": _jsonable(trade_ts),
        "trade": _jsonable(trade),
        "work_items": [_jsonable(w) for w in work],
        "market_as_of": _jsonable(market[0]) if market else None,
        "wallet": _jsonable(wallet[0]) if wallet else None,
        "proxy_funding_recent": [_jsonable(f) for f in funding],
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _issue_flags(pack: Mapping[str, Any]) -> list[str]:
    flags: list[str] = []
    for gap in pack["acquisition"]["gaps_by_class_reason"]:
        if gap["reason"] == "restart-beyond-horizon" and gap["n"] > 0:
            flags.append("restart_beyond_horizon_gaps")
        if gap["reason"] == "horizon-expired" and gap["n"] > 0:
            flags.append("horizon_expired_gaps")
    if pack["acquisition"]["inserts"] == 0:
        flags.append("zero_inserts_in_window")
    sanity = pack["price_size_sanity"]
    if sanity["price_out_of_unit"] > 0:
        flags.append("price_outside_unit_interval")
    if sanity["nonpositive_size"] > 0:
        flags.append("nonpositive_size")
    for label in (
        "window_trades",
        "completed_enrichment_trades",
        "early_lens",
        "production_lens",
    ):
        unexpected = pack[label].get("unexpected_values") or []
        if unexpected:
            flags.append(f"unexpected_values:{label}")
    if pack["markets"].get("unexpected_values"):
        flags.append("unexpected_values:markets")
    queue = pack["featuring_queue"]
    insert_done = sum(
        r["n"]
        for r in queue["work_items_by_trigger_status"]
        if r["trigger"] == "insert_time" and r["status"] == "completed"
    )
    upgrade_done = sum(
        r["n"]
        for r in queue["work_items_by_trigger_status"]
        if r["trigger"] == "regime_upgrade" and r["status"] == "completed"
    )
    if upgrade_done > insert_done and insert_done + upgrade_done > 0:
        flags.append("regime_upgrade_outpaces_insert_time")
    early_n = pack["early_lens"]["cohort_n"]
    if early_n == 0 and pack["acquisition"]["inserts"] > 100:
        flags.append("early_lens_empty_despite_volume")
    arms = pack["early_lens"]["completed_arm_mix"]
    if arms["completed"] > 0 and arms["pct_expected_partial_stub_mix"] is not None:
        if arms["pct_expected_partial_stub_mix"] < 80:
            flags.append("completed_arm_mix_unexpected")
    regime = pack["window_trades"]["categorical"].get("info_knowability_regime") or {}
    trade_n = sum(regime.values())
    unknown_n = int(regime.get("unknown") or 0)
    markets_classified = sum(
        int(v)
        for k, v in (pack["markets"]["categorical"].get("info_knowability_regime") or {}).items()
        if k != "unknown"
    )
    if trade_n > 100 and unknown_n == trade_n and markets_classified > 0:
        flags.append("trades_all_unknown_while_markets_classified")
    return flags


def build_report(mark: datetime, ended: datetime) -> dict[str, Any]:
    with _engine().connect() as conn:
        acquisition = _acquisition(conn, mark, ended)
        queue = _queue(conn, mark, ended)
        markets = _markets_pack(conn, mark, ended)
        sanity = _price_size_sanity(conn, mark, ended)
        window = _all_trade_fields(conn, mark, ended)
        completed = _all_trade_fields(conn, mark, ended, completed_only=True)
        early_fields = _all_trade_fields(conn, mark, ended, min_notional=EARLY_CUTOFF)
        prod_fields = _all_trade_fields(conn, mark, ended, min_notional=PROD_CUTOFF)
        early_n = _cohort_count(conn, mark, ended, min_notional=EARLY_CUTOFF)
        prod_n = _cohort_count(conn, mark, ended, min_notional=PROD_CUTOFF)
        early_arms = _completed_arm_mix(conn, mark, ended, min_notional=EARLY_CUTOFF)
        prod_arms = _completed_arm_mix(conn, mark, ended, min_notional=PROD_CUTOFF)
        gallery = _gallery(conn, mark, ended)
    pack: dict[str, Any] = {
        "run_meta": {
            "mark": mark.isoformat(),
            "ended_at": ended.isoformat(),
            "wall_seconds": round((ended - mark).total_seconds(), 1),
            "early_cutoff_usdc": EARLY_CUTOFF,
            "production_cutoff_usdc": PROD_CUTOFF,
            "framework_phase": "007-featured-enrichment",
            "framework_note": (
                "Key-field catalogs and allowlists evolve with later phases;"
                " regenerate this pack after Core/Useful field ships."
            ),
        },
        "acquisition": acquisition,
        "price_size_sanity": sanity,
        "featuring_queue": queue,
        "markets": markets,
        "window_trades": window,
        "completed_enrichment_trades": completed,
        "early_lens": {
            "cohort_n": early_n,
            "completed_arm_mix": early_arms,
            **early_fields,
        },
        "production_lens": {
            "cohort_n": prod_n,
            "completed_arm_mix": prod_arms,
            **prod_fields,
        },
        "sample_gallery": gallery,
    }
    pack["issue_flags"] = _issue_flags(pack)
    return pack


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mark", help="ISO-8601 run mark UTC")
    parser.add_argument("--mark-file", type=Path, help="File containing run mark")
    parser.add_argument("--ended-at", help="ISO-8601 end bound UTC (default: now)")
    parser.add_argument("--out", type=Path, help="Write JSON report to this path")
    args = parser.parse_args()
    if not args.mark and not args.mark_file:
        raise SystemExit("provide --mark or --mark-file")
    mark_raw = args.mark or args.mark_file.read_text(encoding="utf-8")
    mark = _load_mark(mark_raw)
    ended = _parse_mark(args.ended_at) if args.ended_at else datetime.now(tz=UTC)
    report = build_report(mark, ended)
    payload = json.dumps(report, indent=2, default=str)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
