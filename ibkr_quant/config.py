from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    env: str = os.getenv("IBKR_QUANT_ENV", "paper")
    webhook_secret: str = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
    db_path: Path = Path(os.getenv("IBKR_QUANT_DB", "var/ibkr_quant.sqlite3"))
    data_root: Path = Path(os.getenv("IBKR_QUANT_DATA_ROOT", "/Users/pengdu/Downloads/data/daily"))
    market_data_dir: Path = Path(os.getenv("MARKET_DATA_DIR", "/Users/pengdu/Downloads"))
    vix_glob: str = os.getenv("VIX_GLOB", "TVC_VIX, 1D*.csv")
    vix3m_glob: str = os.getenv("VIX3M_GLOB", "CBOE_DLY_VIX3M, 1D*.csv")
    s5th_glob: str = os.getenv("S5TH_GLOB", "INDEX_S5TH, 1D*.csv")
    s5fi_glob: str = os.getenv("S5FI_GLOB", "INDEX_S5FI, 1D*.csv")
    s5tw_glob: str = os.getenv("S5TW_GLOB", "INDEX_S5TW, 1D*.csv")

    ib_host: str = os.getenv("IB_HOST", "127.0.0.1")
    ib_port: int = int(os.getenv("IB_PORT", "7497"))
    ib_client_id: int = int(os.getenv("IB_CLIENT_ID", "21"))
    ib_account: str | None = os.getenv("IB_ACCOUNT") or None
    execution_adapter: str = os.getenv("EXECUTION_ADAPTER", "mock")

    max_account_usage: float = float(os.getenv("MAX_ACCOUNT_USAGE", "0.95"))
    max_symbol_weight: float = float(os.getenv("MAX_SYMBOL_WEIGHT", "0.25"))
    max_daily_orders: int = int(os.getenv("MAX_DAILY_ORDERS", "30"))
    max_price_deviation_pct: float = float(os.getenv("MAX_PRICE_DEVIATION_PCT", "0.03"))
    min_order_value: float = float(os.getenv("MIN_ORDER_VALUE", "100"))
    data_max_age_minutes: int = int(os.getenv("DATA_MAX_AGE_MINUTES", "1440"))
    order_type: str = os.getenv("ORDER_TYPE", "LMT")
    allow_outside_rth: bool = _bool_env("ALLOW_OUTSIDE_RTH", True)
    after_hours_limit_offset_pct: float = float(os.getenv("AFTER_HOURS_LIMIT_OFFSET_PCT", "0.005"))
    kill_switch: bool = _bool_env("KILL_SWITCH", False)

    ema_state_path: Path = Path(os.getenv("EMA_STATE_PATH", "var/ema_state.json"))

    enable_mean: bool = _bool_env("ENABLE_MEAN", True)
    enable_live_trading: bool = _bool_env("ENABLE_LIVE_TRADING", False)


def load_config() -> AppConfig:
    return AppConfig()
