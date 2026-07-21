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

        meta_data  = quote.get("metaData", {})
        trade_info = quote.get("tradeInfo", {})
        price_info = quote.get("priceInfo", {})
        sec_info   = quote.get("secInfo", {})

        current_price = meta_data.get("lastPrice") or trade_info.get("lastPrice")
        pe            = float(sec_info["pdSymbolPe"]) if sec_info.get("pdSymbolPe") else None
        industry_pe   = float(sec_info["pdSectorPe"]) if sec_info.get("pdSectorPe") else None
        eps           = round(current_price / pe, 2) if current_price and pe else None

        data = {
            "ticker":                  f"{symbol}.NS",
            "company_name":            meta_data.get("companyName", symbol),
            "sector":                  sec_info.get("sector"),
            "industry":                sec_info.get("basicIndustry"),
            "current_price":           current_price,
            "day_high":                meta_data.get("dayHigh"),
            "day_low":                 meta_data.get("dayLow"),
            "fifty_two_week_high":     price_info.get("yearHigh"),
            "fifty_two_week_low":      price_info.get("yearLow"),
            "previous_close":          meta_data.get("previousClose"),
            "market_cap":              trade_info.get("totalMarketCap"),
            "pe_ratio":                pe,
            "industry_pe":             industry_pe,
            "peg_ratio":               None,
            "price_to_book":           None,
            "ev_ebitda":               None,
            "enterprise_value":        None,
            "eps":                     eps,
            "book_value_per_share":    None,
            "dividend_yield":          None,
            "face_value":              trade_info.get("faceValue"),
            "roe":                     None,
            "roce":                    None,
            "roe_3yr":                 None,
            "opm":                     None,
            "opm_last_year":           None,
            "npm":                     None,
            "npm_last_year":           None,
            "gross_margin":            None,
            "ebitda_margin":           None,
            "sales_growth":            None,
            "sales_growth_3yr":        None,
            "profit_growth":           None,
            "profit_growth_3yr":       None,
            "earnings_growth_yoy":     None,
            "revenue_growth_yoy":      None,
            "debt_to_equity":          None,
            "interest_coverage":       None,
            "current_ratio":           None,
            "quick_ratio":             None,
            "total_debt":              None,
            "cash_and_equivalents":    None,
            "promoter_holding":        None,
            "promoter_holding_change": None,
            "pledged_percentage":      None,
            "fii_holding":             None,
            "dii_holding":             None,
            "free_cashflow":           None,
            "operating_cashflow":      None,
            "analyst_target_price":    None,
            "analyst_recommendation":  None,
            "beta":                    None,
            "last_updated":            datetime.now().isoformat()
        }
        return data

    except Exception as e:
        print(f"  Error fetching {symbol}: {e}")
        return None

def fetch_price_history(symbol, days=365):
    try:
        end   = date.today()
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
                "ticker":      f"{symbol}.NS",
                "date":        row.get("mTIMESTAMP", "")[:10],
                "open_price":  row.get("mOpen"),
                "high_price":  row.get("mHigh"),
                "low_price":   row.get("mLow"),
                "close_price": row.get("mClose"),
                "volume":      row.get("mVolume", 0)
            })
        return records

    except Exception as e:
        print(f"  Price history error for {symbol}: {e}")
        return []

def upsert_stock(data):
    conn = get_connection()
    cursor = conn.cursor()
    columns      = ", ".join(data.keys())
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
    failed  = []

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
