import requests
import yfinance as yf
import pandas as pd
import time
from datetime import datetime
from backend.database import get_connection

# browser headers — tricks Yahoo into thinking it's a real user
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://finance.yahoo.com/',
    'Origin': 'https://finance.yahoo.com',
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

TICKERS = [
    "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS",
    "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "BAJFINANCE.NS",
    "HINDUNILVR.NS", "NESTLEIND.NS", "TITAN.NS", "ASIANPAINT.NS",
    "LT.NS", "CUMMINSIND.NS",
    "SUNPHARMA.NS", "DIVISLAB.NS",
    "MARUTI.NS", "BAJAJ-AUTO.NS",
    "PIDILITIND.NS", "RELIANCE.NS"
]

def safe_get(info, key, default=None):
    val = info.get(key, default)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return val

def fetch_yahoo_info(ticker_symbol):
    """
    Fetch stock info directly from Yahoo Finance chart API
    using browser headers — bypasses the 429 block on server IPs
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}"
    params = {
        "interval": "1d",
        "range": "5d",
        "includePrePost": "false",
    }
    try:
        r = SESSION.get(url, params=params, timeout=10)
        if r.status_code == 429:
            print(f"  Rate limited on {ticker_symbol}, waiting 15s...")
            time.sleep(15)
            r = SESSION.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        return meta
    except Exception as e:
        print(f"  Chart API error for {ticker_symbol}: {e}")
        return None

def fetch_yahoo_summary(ticker_symbol):
    """
    Fetch fundamental data from Yahoo Finance quoteSummary API
    with browser headers
    """
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker_symbol}"
    params = {
        "modules": "financialData,defaultKeyStatistics,summaryDetail,assetProfile",
        "corsDomain": "finance.yahoo.com",
        "formatted": "false",
    }

    try:
        r = SESSION.get(url, params=params, timeout=15)

        print("\n" + "=" * 80)
        print(f"SUMMARY REQUEST FOR: {ticker_symbol}")
        print("Status:", r.status_code)
        print("Content-Type:", r.headers.get("Content-Type"))
        print("Response (first 1000 chars):")
        print(r.text[:1000])
        print("=" * 80)

        if r.status_code == 429:
            print(f"Rate limited on {ticker_symbol}, retrying...")
            time.sleep(15)
            r = SESSION.get(url, params=params, timeout=15)

        if r.status_code != 200:
            print("Non-200 response")
            return {}

        data = r.json()

        print("Parsed JSON:")
        print(data)

        result = data.get("quoteSummary", {}).get("result")

        if result is None:
            print("Yahoo returned result=None")
            print("Error:", data.get("quoteSummary", {}).get("error"))
            return {}

        combined = {}
        for module in result:
            combined.update(module)

        return combined

    except Exception as e:
        print(f"Summary API exception: {e}")
        return {}

def calculate_cagr(start_value, end_value, years):
    try:
        if start_value and end_value and start_value > 0 and years > 0:
            return ((end_value / start_value) ** (1 / years) - 1) * 100
        return None
    except:
        return None

def calculate_roce(ticker_obj):
    try:
        financials = ticker_obj.financials
        balance = ticker_obj.balance_sheet
        if financials is None or balance is None:
            return None
        if financials.empty or balance.empty:
            return None
        ebit_row = financials.loc["Operating Income"] if "Operating Income" in financials.index else None
        if ebit_row is None:
            return None
        ebit = ebit_row.iloc[0]
        total_assets = balance.loc["Total Assets"].iloc[0] if "Total Assets" in balance.index else None
        curr_liab = balance.loc["Current Liabilities"].iloc[0] if "Current Liabilities" in balance.index else None
        if total_assets and curr_liab:
            capital_employed = total_assets - curr_liab
            if capital_employed > 0:
                return round((ebit / capital_employed) * 100, 2)
        return None
    except:
        return None

def calculate_growth_metrics(ticker_obj):
    try:
        financials = ticker_obj.financials
        if financials is None or financials.empty:
            return None, None
        sales_cagr_3yr = None
        profit_cagr_3yr = None
        if "Total Revenue" in financials.index:
            revenue = financials.loc["Total Revenue"]
            if len(revenue) >= 4:
                sales_cagr_3yr = calculate_cagr(revenue.iloc[3], revenue.iloc[0], 3)
        if "Net Income" in financials.index:
            profit = financials.loc["Net Income"]
            if len(profit) >= 4:
                profit_cagr_3yr = calculate_cagr(profit.iloc[3], profit.iloc[0], 3)
        return sales_cagr_3yr, profit_cagr_3yr
    except:
        return None, None

def fetch_stock_data(ticker_symbol):
    """
    Main fetch function — uses direct Yahoo Finance API calls
    with browser headers to avoid 429 blocks on server IPs
    """
    print(f"Fetching {ticker_symbol}...")
    try:
        # price data from chart API
        meta = fetch_yahoo_info(ticker_symbol)
        time.sleep(1)

        # fundamental data from quoteSummary API  
        summary = fetch_yahoo_summary(ticker_symbol)
        time.sleep(1)

        financial_data = summary.get("financialData", {})
        key_stats = summary.get("defaultKeyStatistics", {})
        summary_detail = summary.get("summaryDetail", {})
        asset_profile = summary.get("assetProfile", {})

        if not meta and not financial_data:
            print(f"  No data for {ticker_symbol}")
            return None

        # try yfinance for derived metrics (financials/balance sheet)
        # these use download() which is less rate-limited
        roce = None
        sales_growth_3yr = None
        profit_growth_3yr = None
        try:
            stock_obj = yf.Ticker(ticker_symbol)
            roce = calculate_roce(stock_obj)
            sales_growth_3yr, profit_growth_3yr = calculate_growth_metrics(stock_obj)
        except:
            pass

        current_price = (
            meta.get("regularMarketPrice") if meta else None
            or financial_data.get("currentPrice", {}).get("raw")
        )

        data = {
            "ticker": ticker_symbol,
            "company_name": meta.get("longName") or meta.get("shortName") or ticker_symbol if meta else ticker_symbol,
            "sector": asset_profile.get("sector"),
            "industry": asset_profile.get("industry"),

            "current_price": current_price,
            "day_high": meta.get("regularMarketDayHigh") if meta else None,
            "day_low": meta.get("regularMarketDayLow") if meta else None,
            "fifty_two_week_high": meta.get("fiftyTwoWeekHigh") if meta else None,
            "fifty_two_week_low": meta.get("fiftyTwoWeekLow") if meta else None,
            "previous_close": meta.get("regularMarketPreviousClose") if meta else None,

            "market_cap": summary_detail.get("marketCap", {}).get("raw"),
            "pe_ratio": summary_detail.get("trailingPE", {}).get("raw"),
            "industry_pe": None,
            "peg_ratio": key_stats.get("pegRatio", {}).get("raw"),
            "price_to_book": key_stats.get("priceToBook", {}).get("raw"),
            "ev_ebitda": key_stats.get("enterpriseToEbitda", {}).get("raw"),
            "enterprise_value": key_stats.get("enterpriseValue", {}).get("raw"),

            "eps": key_stats.get("trailingEps", {}).get("raw"),
            "book_value_per_share": key_stats.get("bookValue", {}).get("raw"),
            "dividend_yield": summary_detail.get("dividendYield", {}).get("raw"),
            "face_value": None,

            "roe": round(financial_data.get("returnOnEquity", {}).get("raw", 0) * 100, 2)
                   if financial_data.get("returnOnEquity", {}).get("raw") else None,
            "roce": roce,
            "roe_3yr": None,
            "opm": round(financial_data.get("operatingMargins", {}).get("raw", 0) * 100, 2)
                   if financial_data.get("operatingMargins", {}).get("raw") else None,
            "opm_last_year": None,
            "npm": round(financial_data.get("profitMargins", {}).get("raw", 0) * 100, 2)
                   if financial_data.get("profitMargins", {}).get("raw") else None,
            "npm_last_year": None,
            "gross_margin": round(financial_data.get("grossMargins", {}).get("raw", 0) * 100, 2)
                            if financial_data.get("grossMargins", {}).get("raw") else None,
            "ebitda_margin": round(financial_data.get("ebitdaMargins", {}).get("raw", 0) * 100, 2)
                             if financial_data.get("ebitdaMargins", {}).get("raw") else None,

            "sales_growth": round(financial_data.get("revenueGrowth", {}).get("raw", 0) * 100, 2)
                            if financial_data.get("revenueGrowth", {}).get("raw") else None,
            "sales_growth_3yr": round(sales_growth_3yr, 2) if sales_growth_3yr else None,
            "profit_growth": round(financial_data.get("earningsGrowth", {}).get("raw", 0) * 100, 2)
                             if financial_data.get("earningsGrowth", {}).get("raw") else None,
            "profit_growth_3yr": round(profit_growth_3yr, 2) if profit_growth_3yr else None,
            "earnings_growth_yoy": None,
            "revenue_growth_yoy": None,

            "debt_to_equity": financial_data.get("debtToEquity", {}).get("raw"),
            "interest_coverage": None,
            "current_ratio": financial_data.get("currentRatio", {}).get("raw"),
            "quick_ratio": financial_data.get("quickRatio", {}).get("raw"),
            "total_debt": financial_data.get("totalDebt", {}).get("raw"),
            "cash_and_equivalents": financial_data.get("totalCash", {}).get("raw"),

            "promoter_holding": None,
            "promoter_holding_change": None,
            "pledged_percentage": None,
            "fii_holding": None,
            "dii_holding": None,

            "free_cashflow": financial_data.get("freeCashflow", {}).get("raw"),
            "operating_cashflow": financial_data.get("operatingCashflow", {}).get("raw"),

            "analyst_target_price": financial_data.get("targetMeanPrice", {}).get("raw"),
            "analyst_recommendation": financial_data.get("recommendationKey"),
            "beta": key_stats.get("beta", {}).get("raw"),

            "last_updated": datetime.now().isoformat()
        }
        return data

    except Exception as e:
        print(f"  Error fetching {ticker_symbol}: {e}")
        return None

def fetch_price_history(ticker_symbol, period="1y"):
    """
    Uses yf.download() — bulk download is more reliable than ticker.history()
    """
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
                "open_price": round(float(row["Open"]), 2),
                "high_price": round(float(row["High"]), 2),
                "low_price": round(float(row["Low"]), 2),
                "close_price": round(float(row["Close"]), 2),
                "volume": int(row["Volume"])
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
    values = list(data.values())
    cursor.execute(f"""
        INSERT OR REPLACE INTO stocks ({columns})
        VALUES ({placeholders})
    """, values)
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
            print(f"  ✓ {ticker} — {data['company_name']}")
        else:
            failed.append(ticker)
        time.sleep(3)
    print(f"\nSeeding complete: {success}/{len(TICKERS)} stocks loaded")
    if failed:
        print(f"Failed: {failed}")

def refresh_prices():
    print("Refreshing prices...")
    for ticker in TICKERS:
        data = fetch_stock_data(ticker)
        if data:
            upsert_stock(data)
        time.sleep(3)
    print("Price refresh complete")
