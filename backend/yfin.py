import requests
import time
import os
from datetime import datetime
from backend.database import get_connection

API_KEY = os.getenv("TWELVE_API_KEY")
BASE_URL = "https://api.twelvedata.com"

# testing with one company first
TICKERS = [
    {"symbol": "TCS", "exchange": "NSE", "ticker_id": "TCS.NS"}
]

def td_get(endpoint, params):
    """
    Central request function for all Twelve Data calls.
    Adds API key, handles errors in one place.
    """
    params["apikey"] = API_KEY
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=10)
        data = r.json()
        if data.get("status") == "error":
            print(f"  Twelve Data error: {data.get('message')}")
            return None
        return data
    except Exception as e:
        print(f"  Request error: {e}")
        return None

def fetch_stock_data(stock):
    """
    Fetches quote + statistics for one stock.
    stock is a dict: {symbol, exchange, ticker_id}
    """
    symbol = stock["symbol"]
    exchange = stock["exchange"]
    ticker_id = stock["ticker_id"]

    print(f"Fetching {symbol} ({exchange})...")

    # quote — price, high, low, volume, 52wk
    quote = td_get("quote", {
        "symbol": symbol,
        "exchange": exchange,
    })

    time.sleep(1)

    # statistics — PE, EPS, market cap, ROE etc
    stats = td_get("statistics", {
        "symbol": symbol,
        "exchange": exchange,
    })

    if not quote:
        print(f"  No quote data for {symbol}")
        return None

    # safely pull from statistics if available
    valuations = {}
    financials = {}
    if stats:
        valuations = stats.get("statistics", {}).get("valuations_metrics", {})
        financials = stats.get("statistics", {}).get("financials", {})

    def safe_float(val):
        try:
            return float(val) if val not in (None, "N/A", "-", "") else None
        except:
            return None

    current_price = safe_float(quote.get("close"))
    pe = safe_float(valuations.get("trailing_pe", {}).get("value"))
    eps = safe_float(financials.get("eps_diluted_ttm", {}).get("value"))
    market_cap = safe_float(valuations.get("market_capitalization", {}).get("value"))
    roe = safe_float(financials.get("return_on_equity_ttm", {}).get("value"))
    debt_to_equity = safe_float(financials.get("total_debt_to_equity", {}).get("value"))
    dividend_yield = safe_float(valuations.get("forward_dividend_yield", {}).get("value"))
    beta = safe_float(stats.get("statistics", {}).get("stock_statistics", {}).get("beta", {}).get("value") if stats else None)
    fifty_two_week = quote.get("fifty_two_week", {})

    data = {
        "ticker": ticker_id,
        "company_name": quote.get("name", symbol),
        "sector": None,
        "industry": None,

        "current_price": current_price,
        "day_high": safe_float(quote.get("high")),
        "day_low": safe_float(quote.get("low")),
        "fifty_two_week_high": safe_float(fifty_two_week.get("high")),
        "fifty_two_week_low": safe_float(fifty_two_week.get("low")),
        "previous_close": safe_float(quote.get("previous_close")),

        "market_cap": market_cap,
        "pe_ratio": pe,
        "industry_pe": None,
        "peg_ratio": safe_float(valuations.get("peg_ratio", {}).get("value")),
        "price_to_book": safe_float(valuations.get("price_to_book_mrq", {}).get("value")),
        "ev_ebitda": safe_float(valuations.get("enterprise_to_ebitda", {}).get("value")),
        "enterprise_value": safe_float(valuations.get("enterprise_value", {}).get("value")),

        "eps": eps,
        "book_value_per_share": None,
        "dividend_yield": dividend_yield,
        "face_value": None,

        "roe": safe_float(financials.get("return_on_equity_ttm", {}).get("value")),
        "roce": None,
        "roe_3yr": None,
        "opm": safe_float(financials.get("operating_margin_ttm", {}).get("value")),
        "opm_last_year": None,
        "npm": safe_float(financials.get("net_profit_margin_ttm", {}).get("value")),
        "npm_last_year": None,
        "gross_margin": safe_float(financials.get("gross_profit_margin_ttm", {}).get("value")),
        "ebitda_margin": None,

        "sales_growth": safe_float(financials.get("revenue_growth_ttm", {}).get("value")),
        "sales_growth_3yr": None,
        "profit_growth": safe_float(financials.get("eps_growth_ttm", {}).get("value")),
        "profit_growth_3yr": None,
        "earnings_growth_yoy": None,
        "revenue_growth_yoy": None,

        "debt_to_equity": debt_to_equity,
        "interest_coverage": None,
        "current_ratio": safe_float(financials.get("current_ratio_mrq", {}).get("value")),
        "quick_ratio": safe_float(financials.get("quick_ratio_mrq", {}).get("value")),
        "total_debt": safe_float(financials.get("total_debt_mrq", {}).get("value")),
        "cash_and_equivalents": safe_float(financials.get("total_cash_mrq", {}).get("value")),

        "promoter_holding": None,
        "promoter_holding_change": None,
        "pledged_percentage": None,
        "fii_holding": None,
        "dii_holding": None,

        "free_cashflow": safe_float(financials.get("free_cash_flow_ttm", {}).get("value")),
        "operating_cashflow": safe_float(financials.get("operating_cash_flow_ttm", {}).get("value")),

        "analyst_target_price": safe_float(stats.get("statistics", {}).get("stock_statistics", {}).get("target_price", {}).get("value") if stats else None),
        "analyst_recommendation": None,
        "beta": beta,

        "last_updated": datetime.now().isoformat()
    }
    return data

def fetch_price_history(stock, period="1y"):
    """
    Fetches daily OHLCV for 1 year.
    Twelve Data uses outputsize (number of bars) not a period string.
    365 bars = ~1 year of daily data.
    """
    symbol = stock["symbol"]
    exchange = stock["exchange"]
    ticker_id = stock["ticker_id"]

    data = td_get("time_series", {
        "symbol": symbol,
        "exchange": exchange,
        "interval": "1day",
        "outputsize": 365,
    })

    if not data or "values" not in data:
        return []

    records = []
    for bar in data["values"]:
        records.append({
            "ticker": ticker_id,
            "date": bar["datetime"],
            "open_price": float(bar["open"]),
            "high_price": float(bar["high"]),
            "low_price": float(bar["low"]),
            "close_price": float(bar["close"]),
            "volume": int(bar["volume"]) if bar.get("volume") else 0
        })
    return records

def upsert_stock(data):
    conn = get_connection()
    cursor = conn.cursor()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?" for _ in data])
    cursor.execute(f"""
        INSERT OR REPLACE INTO stocks ({columns})
        VALUES ({placeholders})
    """, list(data.values()))
    conn.commit()
    conn.close()

def upsert_price_history(records):
    if not records:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT OR IGNORE INTO price_history
        (ticker, date, open_price, high_price, low_price, close_price, volume)
        VALUES (:ticker, :date, :open_price, :high_price, :low_price, :close_price, :volume)
    """, records)
    conn.commit()
    conn.close()

def seed_all_stocks():
    print(f"Seeding {len(TICKERS)} stocks...")
    success = 0
    failed = []

    for stock in TICKERS:
        data = fetch_stock_data(stock)
        if data:
            upsert_stock(data)
            history = fetch_price_history(stock)
            upsert_price_history(history)
            success += 1
            print(f"  ✓ {stock['ticker_id']} — {data['company_name']}")
        else:
            failed.append(stock["ticker_id"])
        time.sleep(2)

    print(f"Seeding complete: {success}/{len(TICKERS)} loaded")
    if failed:
        print(f"Failed: {failed}")

def refresh_prices():
    for stock in TICKERS:
        data = fetch_stock_data(stock)
        if data:
            upsert_stock(data)
        time.sleep(2)
