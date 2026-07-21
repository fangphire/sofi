import time
from datetime import datetime, date, timedelta
from pathlib import Path
from nse import NSE
from backend.database import get_connection

TICKERS = ["TCS"]

COOKIE_DIR = Path("/tmp/nse_cookies")
COOKIE_DIR.mkdir(exist_ok=True)

def fetch_stock_data(symbol):
    print(f"Fetching {symbol}...")
    try:
        with NSE(download_folder=COOKIE_DIR, server=True) as nse:
            quote = nse.quote(symbol)
            time.sleep(1)
            meta = nse.equityMetaInfo(symbol)

        import json
        print("QUOTE KEYS:", list(quote.keys()))
        print("QUOTE SAMPLE:", json.dumps(quote, indent=2)[:3000])
        print("META:", json.dumps(meta, indent=2)[:1000])
        return None

    except Exception as e:
        print(f"  Error fetching {symbol}: {e}")
        return None
        
def fetch_price_history(symbol, days=365):
    try:
        end = date.today()
        start = end - timedelta(days=days)

        with NSE(download_folder=COOKIE_DIR, server=True) as nse:
            hist = nse.fetch_equity_historical_data(
                symbol=symbol,
                from_date=start,
                to_date=end
            )

        if not hist:
            return []

        records = []
        for row in hist:
            records.append({
                "ticker": f"{symbol}.NS",
                "date": row.get("mTIMESTAMP", "")[:10],
                "open_price": row.get("mOpen"),
                "high_price": row.get("mHigh"),
                "low_price": row.get("mLow"),
                "close_price": row.get("mClose"),
                "volume": row.get("mVolume", 0)
            })
        return records

    except Exception as e:
        print(f"  Price history error for {symbol}: {e}")
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

    for symbol in TICKERS:
        data = fetch_stock_data(symbol)
        if data:
            upsert_stock(data)
            history = fetch_price_history(symbol)
            upsert_price_history(history)
            success += 1
            print(f"  ✓ {symbol} — {data['company_name']}")
        else:
            failed.append(symbol)
        time.sleep(1)

    print(f"Seeding complete: {success}/{len(TICKERS)} loaded")
    if failed:
        print(f"Failed: {failed}")

def refresh_prices():
    for symbol in TICKERS:
        data = fetch_stock_data(symbol)
        if data:
            upsert_stock(data)
        time.sleep(1)
