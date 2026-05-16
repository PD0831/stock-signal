from __future__ import annotations

from datetime import date


# Full NAS100 members by year (point-in-time, annual snapshot).
# Used for ADV-based stock selection in the dual sub-portfolio live strategy.
# Source: Nasdaq-100 historical compositions. For live trading 2025-2026 is sufficient;
# earlier years are included for backtest consistency with existing scripts.
NAS100_FULL_BY_YEAR: dict[int, tuple[str, ...]] = {
    2026: (
        "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
        "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR",
        "CCEP", "CDNS", "CEG", "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP", "CSX",
        "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC", "FANG", "FAST", "FTNT",
        "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "ILMN", "INTC", "INTU",
        "ISRG", "KDP", "KLAC", "LIN", "LRCX", "LULU", "MAR", "MCHP", "MDLZ", "MELI",
        "META", "MNST", "MRNA", "MRVL", "MSFT", "MU", "NFLX", "NVDA", "NXPI", "ODFL",
        "ON", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PYPL", "QCOM", "REGN",
        "ROP", "ROST", "SBUX", "SNPS", "TEAM", "TMUS", "TSLA", "TTD", "TXN", "VRSK",
        "VRTX", "WDAY", "WBD", "XEL", "ZS",
    ),
    2025: (
        "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
        "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR",
        "CCEP", "CDNS", "CEG", "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP", "CSX",
        "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC", "FANG", "FAST", "FTNT",
        "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "ILMN", "INTC", "INTU",
        "ISRG", "KDP", "KLAC", "LIN", "LRCX", "LULU", "MAR", "MCHP", "MDLZ", "MELI",
        "META", "MNST", "MRNA", "MRVL", "MSFT", "MU", "NFLX", "NVDA", "NXPI", "ODFL",
        "ON", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PYPL", "QCOM", "REGN",
        "ROP", "ROST", "SBUX", "SNPS", "TEAM", "TMUS", "TSLA", "TTD", "TXN", "VRSK",
        "VRTX", "WDAY", "WBD", "XEL", "ZS",
    ),
    2024: (
        "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
        "AMZN", "ANSS", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR", "CDNS", "CEG",
        "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP", "CSX", "CTAS", "CTSH", "DDOG",
        "DXCM", "EA", "EXC", "FANG", "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG",
        "GOOGL", "HON", "IDXX", "ILMN", "INTC", "INTU", "ISRG", "KDP", "KLAC", "LIN",
        "LRCX", "LULU", "MAR", "MCHP", "MDLZ", "MELI", "META", "MNST", "MRNA", "MRVL",
        "MSFT", "MU", "NFLX", "NVDA", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX",
        "PCAR", "PDD", "PEP", "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SNPS",
        "TEAM", "TMUS", "TSLA", "TTD", "TXN", "VRSK", "VRTX", "WDAY", "WBD", "XEL", "ZS",
    ),
    2023: (
        "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
        "AMZN", "ANSS", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR", "CDNS", "CEG",
        "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP", "CSX", "CTAS", "CTSH", "DDOG",
        "DXCM", "EA", "EXC", "FANG", "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG",
        "GOOGL", "HON", "IDXX", "ILMN", "INTC", "INTU", "ISRG", "KDP", "KLAC", "LIN",
        "LRCX", "LULU", "MAR", "MCHP", "MDLZ", "MELI", "META", "MNST", "MRNA", "MRVL",
        "MSFT", "MU", "NFLX", "NVDA", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX",
        "PCAR", "PEP", "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SNPS", "TEAM",
        "TMUS", "TSLA", "TTD", "TXN", "VRSK", "VRTX", "WDAY", "XEL", "ZS",
    ),
}


def nas100_members_on(as_of: date) -> tuple[str, ...]:
    years = sorted(NAS100_FULL_BY_YEAR)
    year = max((y for y in years if y <= as_of.year), default=years[-1])
    return NAS100_FULL_BY_YEAR[year]


QQQ_TOP10_BY_YEAR_PROXY: dict[int, tuple[str, ...]] = {
    2006: ("MSFT", "CSCO", "INTC", "ORCL", "DELL", "QCOM", "AMGN", "AAPL", "EBAY", "SBUX"),
    2007: ("MSFT", "CSCO", "INTC", "ORCL", "DELL", "AAPL", "GOOGL", "QCOM", "AMGN", "GILD"),
    2008: ("MSFT", "CSCO", "INTC", "ORCL", "DELL", "AAPL", "GOOGL", "QCOM", "AMGN", "GILD"),
    2009: ("MSFT", "CSCO", "INTC", "ORCL", "DELL", "AAPL", "GOOGL", "QCOM", "AMGN", "GILD"),
    2010: ("MSFT", "CSCO", "INTC", "AAPL", "GOOGL", "ORCL", "AMZN", "QCOM", "CMCSA", "AMGN"),
    2011: ("MSFT", "CSCO", "INTC", "AAPL", "GOOGL", "ORCL", "AMZN", "QCOM", "CMCSA", "AMGN"),
    2012: ("MSFT", "CSCO", "INTC", "AAPL", "GOOGL", "ORCL", "AMZN", "QCOM", "CMCSA", "AMGN"),
    2013: ("AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "AMZN", "META", "CMCSA", "AMGN", "PEP"),
    2014: ("AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "AMZN", "META", "CMCSA", "AMGN", "PEP"),
    2015: ("AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "AMZN", "META", "CMCSA", "AMGN", "PEP"),
    2016: ("AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "AMZN", "META", "CMCSA", "AMGN", "PEP"),
    2017: ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "INTC", "CSCO", "CMCSA", "PEP", "NFLX"),
    2018: ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "INTC", "CSCO", "CMCSA", "PEP", "NFLX"),
    2019: ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "INTC", "CSCO", "CMCSA", "PEP", "NFLX"),
    2020: ("AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "PEP", "COST", "AVGO"),
    2021: ("AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "PEP", "COST", "AVGO"),
    2022: ("AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "PEP", "COST", "AVGO"),
    2023: ("AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "NVDA", "META", "AVGO", "COST", "NFLX"),
    2024: ("AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "NVDA", "META", "AVGO", "COST", "NFLX"),
    2025: ("MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "COST", "NFLX"),
    2026: ("NVDA", "AAPL", "MSFT", "AMZN", "AVGO", "GOOGL", "META", "TSLA", "GOOG", "WMT"),
}


def qqq_top10_on(as_of: date) -> tuple[str, ...]:
    years = sorted(QQQ_TOP10_BY_YEAR_PROXY)
    year = max((item for item in years if item <= as_of.year), default=years[0])
    return QQQ_TOP10_BY_YEAR_PROXY[year]


def qqq_market_cap_top5_on(as_of: date) -> tuple[str, ...]:
    return qqq_top10_on(as_of)[:5]

