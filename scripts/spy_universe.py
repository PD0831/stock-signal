"""SPY holdings universe helpers for S&P 500 breadth.

The breadth chart is calibrated from the official SPDR SPY holdings workbook.
The workbook can contain non-equity bookkeeping rows, so this module returns
both the tradable equity symbols and diagnostics about excluded rows.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Iterable
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

SPY_HOLDINGS_XLSX_URL = (
    "https://www.ssga.com/us/en/intermediary/etfs/library-content/"
    "products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
}

_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_EXCLUDED_TICKERS = {"", "-", "USD", "CASH_USD"}


@dataclass(frozen=True)
class SpyUniverse:
    symbols: list[str]
    as_of: str | None
    raw_holding_rows: int
    excluded_rows: list[dict[str, str]]

    @property
    def excluded_count(self) -> int:
        return len(self.excluded_rows)


def normalize_symbol(value: object) -> str | None:
    if value is None:
        return None
    symbol = str(value).strip().upper().replace(".", "-")
    if not symbol or symbol in _EXCLUDED_TICKERS:
        return None
    return symbol


def _column_name(cell_ref: str) -> str:
    return "".join(ch for ch in cell_ref if ch.isalpha())


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for si in root.findall("a:si", _NS):
        text = "".join(t.text or "" for t in si.findall(".//a:t", _NS))
        values.append(text)
    return values


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    value = cell.find("a:v", _NS)
    raw = value.text if value is not None else ""
    if cell.attrib.get("t") == "s" and raw:
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return raw
    inline = cell.find("a:is", _NS)
    if inline is not None:
        return "".join(t.text or "" for t in inline.findall(".//a:t", _NS))
    return raw or ""


def _worksheet_rows(data: bytes) -> Iterable[list[str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        shared = _shared_strings(zf)
        sheet_name = "xl/worksheets/sheet1.xml"
        root = ET.fromstring(zf.read(sheet_name))
        for row in root.findall(".//a:sheetData/a:row", _NS):
            values_by_col = {
                _column_name(cell.attrib.get("r", "")): _cell_value(cell, shared).strip()
                for cell in row.findall("a:c", _NS)
            }
            if not values_by_col:
                continue
            columns = sorted(values_by_col, key=lambda c: sum((ord(ch) - 64) * (26 ** i) for i, ch in enumerate(reversed(c))))
            max_idx = max(sum((ord(ch) - 64) * (26 ** i) for i, ch in enumerate(reversed(c))) for c in columns)
            out = [""] * max_idx
            for col, value in values_by_col.items():
                idx = sum((ord(ch) - 64) * (26 ** i) for i, ch in enumerate(reversed(col))) - 1
                out[idx] = value
            yield out


def parse_spy_holdings_xlsx(data: bytes) -> SpyUniverse:
    rows = list(_worksheet_rows(data))
    as_of = None
    header_index = None

    for i, row in enumerate(rows):
        joined = " ".join(row)
        if "Holdings:" in joined and "As of" in joined:
            as_of = joined.split("As of", 1)[-1].strip()
        normalized = [value.strip() for value in row]
        if {"Name", "Ticker"}.issubset(set(normalized)):
            header_index = i
            break

    if header_index is None:
        raise ValueError("Could not find SPY holdings header row")

    headers = [value.strip() for value in rows[header_index]]
    name_idx = headers.index("Name")
    ticker_idx = headers.index("Ticker")
    currency_idx = headers.index("Local Currency") if "Local Currency" in headers else None

    symbols: list[str] = []
    excluded: list[dict[str, str]] = []
    raw_holding_rows = 0

    for row in rows[header_index + 1:]:
        if len(row) <= max(name_idx, ticker_idx):
            continue
        name = row[name_idx].strip()
        raw_ticker = row[ticker_idx].strip()
        currency = row[currency_idx].strip() if currency_idx is not None and len(row) > currency_idx else ""
        if not name and not raw_ticker:
            continue
        raw_holding_rows += 1
        symbol = normalize_symbol(raw_ticker)
        reason = ""
        if not symbol:
            reason = "blank_or_cash_ticker"
        elif name.upper().startswith("CONTRA"):
            reason = "contra_bookkeeping_row"
        elif not _TICKER_RE.match(symbol):
            reason = "non_ticker_identifier"
        elif currency and currency != "USD":
            reason = f"non_usd_currency:{currency}"

        if reason:
            excluded.append({"name": name, "ticker": raw_ticker, "currency": currency, "reason": reason})
            continue
        symbols.append(symbol)

    return SpyUniverse(
        symbols=sorted(dict.fromkeys(symbols)),
        as_of=as_of,
        raw_holding_rows=raw_holding_rows,
        excluded_rows=excluded,
    )


def download_spy_universe(url: str = SPY_HOLDINGS_XLSX_URL) -> SpyUniverse:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=45) as response:
        data = response.read()
    return parse_spy_holdings_xlsx(data)
