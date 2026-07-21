import yfinance as yf
import pandas as pd
import time
from datetime import datetime
from backend.database import get_connection

TICKERS = [
    "TCS.NS",  # testing with one company first
]

def fetch_stock_data(ticker_symbol):
    print(f"Fetching {ticker_symbol}...")
    try:
        stock = yf.Ticker(ticker_symbol)
        fi = stock.fast_info

        price = fi.last_price
        pe = fi.pe_ratio if hasattr(fi, 'pe_ratio') else None
        eps = round(price / pe, 2) if price and pe else None

        data = {
            "ticker": ticker_symbol,
            "company_name": ticker_symbol.replace(".NS", ""),
            "sector": None,
            "industry": None,
            "current_price": round(price, 2) if price else None,
            "day_high": round(fi.day_high, 2) if fi.day_high else None,
            "day_low": round(fi.day_low, 2) if fi.day_low else None,
            "fifty_two_week_high": round(fi.year_high, 2) if fi.year_high else None,
            "fifty_two_week_low": round(fi.year_low, 2) if fi.year_low else None,
            "previous_close": round(fi.previous_close, 2) if fi.previous_close else None,
            "market_cap": fi.market_cap,
            "pe_ratio": round(pe, 2) if pe else None,
            "industry_pe": None,
            "peg_ratio": None,
            "price_to_book": None,
            "ev_ebitda": None,
            "enterprise_value": None,
            "eps": eps,
            "book_value_per_share": None,
            "dividend_yield": None,
            "face_value": None,
            "roe": None,
            "roce": None,
            "roe_3yr": None,
            "opm": None,
            "opm_last_year": None,
            "npm": None,
            "npm_last_year": None,
            "gross_margin": None,
            "ebitda_margin": None,
            "sales_growth": None,
            "sales_growth_3yr": None,
            "profit_growth": None,
            "profit_growth_3yr": None,
            "earnings_growth_yoy": None,
            "revenue_growth_yoy": None,
            "debt_to_equity": None,
            "interest_coverage": None,
            "current_ratio": None,
            "quick_ratio": None,
            "total_debt": None,
            "cash_and_equivalents": None,
            "promoter_holding": None,
            "promoter_holding_change": None,
            "pledged_percentage": None,
            "fii_holding": None,
            "dii_holding": None,
            "free_cashflow": None,
            "operating_cashflow": None,
            "analyst_target_price": None,
            "analyst_recommendation": None,
            "beta": None,
            "last_updated": datetime.now().isoformat()
        }
        return data

    except Exception as e:
        print(f"  Error fetching {ticker_symbol}: {e}")
        return None

def fetch_price_history(ticker_symbol, period="1y"):
    try:
        hist = yf.download(
            ticker_symbol,
            period=period,
            auto_adjust=True,
            progress=False
        )
        if hist.empty:
            return []
        records = []
        for date, row in hist.iterrows():
            records.append({
                "ticker": ticker_symbol,
                "date": date.strftime("%Y-%m-%d"),
                "open_price": round(float(row["Open"].iloc[0] if hasattr(row["Open"], 'iloc') else row["Open"]), 2),
                "high_price": round(float(row["High"].iloc[0] if hasattr(row["High"], 'iloc') else row["High"]), 2),
                "low_price": round(float(row["Low"].iloc[0] if hasattr(row["Low"], 'iloc') else row["Low"]), 2),
                "close_price": round(float(row["Close"].iloc[0] if hasattr(row["Close"], 'iloc') else row["Close"]), 2),
                "volume": int(row["Volume"].iloc[0] if hasattr(row["Volume"], 'iloc') else row["Volume"])
            })
        return records
    except Exception as e:
        print(f"  Price history error for {ticker_symbol}: {e}")
        return []

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
    for ticker in TICKERS:
        data = fetch_stock_data(ticker)
        if data:
            upsert_stock(data)
            history = fetch_price_history(ticker)
            upsert_price_history(history)
            success += 1
            print(f"  ✓ {ticker}")
        else:
            failed.append(ticker)
        time.sleep(2)
    print(f"Seeding complete: {success}/{len(TICKERS)} loaded")
    if failed:
        print(f"Failed: {failed}")

def refresh_prices():
    for ticker in TICKERS:
        data = fetch_stock_data(ticker)
        if data:
            upsert_stock(data)
        time.sleep(2)
