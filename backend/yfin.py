import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from backend.database import get_connection

TICKERS = [
    # Large cap — IT
    "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS",
    # Large cap — Banking & Finance
    "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "BAJFINANCE.NS",
    # Large cap — Consumer & Retail
    "HINDUNILVR.NS", "NESTLEIND.NS", "TITAN.NS", "ASIANPAINT.NS",
    # Mid cap — Capital Goods & Infra
    "LT.NS", "CUMMINSIND.NS",
    # Mid cap — Pharma
    "SUNPHARMA.NS", "DIVISLAB.NS",
    # Mid cap — Auto
    "MARUTI.NS", "BAJAJ-AUTO.NS",
    # Mid cap — Chemicals & Energy
    "PIDILITIND.NS", "RELIANCE.NS"
]

def safe_get(info, key, default=None):
    """Safely extract a value from yfinance info dict"""
    val = info.get(key, default)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return val

def calculate_cagr(start_value, end_value, years):
    """Calculate Compound Annual Growth Rate"""
    try:
        if start_value and end_value and start_value > 0 and years > 0:
            return ((end_value / start_value) ** (1 / years) - 1) * 100
        return None
    except:
        return None

def calculate_roce(ticker_obj):
    """
    ROCE = EBIT / Capital Employed
    Capital Employed = Total Assets - Current Liabilities
    EBIT = Operating Income from income statement
    """
    try:
        financials = ticker_obj.financials
        balance = ticker_obj.balance_sheet

        if financials is None or balance is None:
            return None
        if financials.empty or balance.empty:
            return None

        # get most recent year's operating income (EBIT)
        ebit_row = financials.loc["Operating Income"] if "Operating Income" in financials.index else None
        if ebit_row is None:
            return None
        ebit = ebit_row.iloc[0]

        # capital employed = total assets - current liabilities
        total_assets = balance.loc["Total Assets"].iloc[0] if "Total Assets" in balance.index else None
        curr_liab = balance.loc["Current Liabilities"].iloc[0] if "Current Liabilities" in balance.index else None

        if total_assets and curr_liab:
            capital_employed = total_assets - curr_liab
            if capital_employed > 0:
                return round((ebit / capital_employed) * 100, 2)
        return None
    except:
        return None

def calculate_interest_coverage(ticker_obj):
    """
    Interest Coverage = EBIT / Interest Expense
    Higher = company can more easily service its debt
    """
    try:
        financials = ticker_obj.financials
        if financials is None or financials.empty:
            return None

        ebit = financials.loc["Operating Income"].iloc[0] if "Operating Income" in financials.index else None
        interest = financials.loc["Interest Expense"].iloc[0] if "Interest Expense" in financials.index else None

        if ebit and interest and interest != 0:
            return round(abs(ebit / interest), 2)
        return None
    except:
        return None

def calculate_growth_metrics(ticker_obj):
    """
    Calculate 3-year CAGR for sales and profit
    yfinance gives us 4 years of annual financials
    so we compare year 0 (most recent) vs year 3 (oldest)
    """
    try:
        financials = ticker_obj.financials
        if financials is None or financials.empty:
            return None, None

        # revenue
        if "Total Revenue" in financials.index:
            revenue = financials.loc["Total Revenue"]
            if len(revenue) >= 4:
                sales_cagr_3yr = calculate_cagr(revenue.iloc[3], revenue.iloc[0], 3)
            else:
                sales_cagr_3yr = None
        else:
            sales_cagr_3yr = None

        # net income
        if "Net Income" in financials.index:
            profit = financials.loc["Net Income"]
            if len(profit) >= 4:
                profit_cagr_3yr = calculate_cagr(profit.iloc[3], profit.iloc[0], 3)
            else:
                profit_cagr_3yr = None
        else:
            profit_cagr_3yr = None

        return sales_cagr_3yr, profit_cagr_3yr
    except:
        return None, None

def calculate_roe_3yr(ticker_obj):
    """Average ROE over last 3 years from financials + equity"""
    try:
        financials = ticker_obj.financials
        balance = ticker_obj.balance_sheet

        if financials is None or balance is None:
            return None
        if financials.empty or balance.empty:
            return None

        net_incomes = financials.loc["Net Income"] if "Net Income" in financials.index else None
        equity = balance.loc["Stockholders Equity"] if "Stockholders Equity" in balance.index else None

        if net_incomes is None or equity is None:
            return None

        roe_values = []
        for i in range(min(3, len(net_incomes), len(equity))):
            if equity.iloc[i] and equity.iloc[i] > 0:
                roe_values.append(net_incomes.iloc[i] / equity.iloc[i] * 100)

        if roe_values:
            return round(sum(roe_values) / len(roe_values), 2)
        return None
    except:
        return None

def fetch_stock_data(ticker_symbol):
    """
    Main function — fetches all data for one stock
    Returns a dict matching our database schema
    """
    print(f"Fetching {ticker_symbol}...")
    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info

        # if yfinance returns empty info, skip this ticker
        if not info or safe_get(info, "regularMarketPrice") is None:
            print(f"  No data returned for {ticker_symbol}")
            return None

        # calculate derived metrics
        roce = calculate_roce(stock)
        interest_coverage = calculate_interest_coverage(stock)
        sales_growth_3yr, profit_growth_3yr = calculate_growth_metrics(stock)
        roe_3yr = calculate_roe_3yr(stock)

        # operating margin last year — from financials if available
        try:
            financials = stock.financials
            if financials is not None and not financials.empty and len(financials.columns) > 1:
                revenue_prev = financials.loc["Total Revenue"].iloc[1] if "Total Revenue" in financials.index else None
                op_income_prev = financials.loc["Operating Income"].iloc[1] if "Operating Income" in financials.index else None
                opm_last_year = round((op_income_prev / revenue_prev) * 100, 2) if revenue_prev and op_income_prev else None

                net_income_prev = financials.loc["Net Income"].iloc[1] if "Net Income" in financials.index else None
                npm_last_year = round((net_income_prev / revenue_prev) * 100, 2) if revenue_prev and net_income_prev else None
            else:
                opm_last_year = None
                npm_last_year = None
        except:
            opm_last_year = None
            npm_last_year = None

        data = {
            # identification
            "ticker": ticker_symbol,
            "company_name": safe_get(info, "longName", ticker_symbol),
            "sector": safe_get(info, "sector"),
            "industry": safe_get(info, "industry"),

            # price
            "current_price": safe_get(info, "currentPrice") or safe_get(info, "regularMarketPrice"),
            "day_high": safe_get(info, "dayHigh"),
            "day_low": safe_get(info, "dayLow"),
            "fifty_two_week_high": safe_get(info, "fiftyTwoWeekHigh"),
            "fifty_two_week_low": safe_get(info, "fiftyTwoWeekLow"),
            "previous_close": safe_get(info, "previousClose"),

            # valuation
            "market_cap": safe_get(info, "marketCap"),
            "pe_ratio": safe_get(info, "trailingPE"),
            "industry_pe": None,  # not available from yfinance — needs screener.in
            "peg_ratio": safe_get(info, "pegRatio"),
            "price_to_book": safe_get(info, "priceToBook"),
            "ev_ebitda": safe_get(info, "enterpriseToEbitda"),
            "enterprise_value": safe_get(info, "enterpriseValue"),

            # per share
            "eps": safe_get(info, "trailingEps"),
            "book_value_per_share": safe_get(info, "bookValue"),
            "dividend_yield": safe_get(info, "dividendYield"),
            "face_value": None,  # not available from yfinance

            # profitability
            "roe": round(safe_get(info, "returnOnEquity", 0) * 100, 2) if safe_get(info, "returnOnEquity") else None,
            "roce": roce,
            "roe_3yr": roe_3yr,
            "opm": round(safe_get(info, "operatingMargins", 0) * 100, 2) if safe_get(info, "operatingMargins") else None,
            "opm_last_year": opm_last_year,
            "npm": round(safe_get(info, "profitMargins", 0) * 100, 2) if safe_get(info, "profitMargins") else None,
            "npm_last_year": npm_last_year,
            "gross_margin": round(safe_get(info, "grossMargins", 0) * 100, 2) if safe_get(info, "grossMargins") else None,
            "ebitda_margin": round(safe_get(info, "ebitdaMargins", 0) * 100, 2) if safe_get(info, "ebitdaMargins") else None,

            # growth
            "sales_growth": round(safe_get(info, "revenueGrowth", 0) * 100, 2) if safe_get(info, "revenueGrowth") else None,
            "sales_growth_3yr": round(sales_growth_3yr, 2) if sales_growth_3yr else None,
            "profit_growth": round(safe_get(info, "earningsGrowth", 0) * 100, 2) if safe_get(info, "earningsGrowth") else None,
            "profit_growth_3yr": round(profit_growth_3yr, 2) if profit_growth_3yr else None,
            "earnings_growth_yoy": round(safe_get(info, "earningsGrowth", 0) * 100, 2) if safe_get(info, "earningsGrowth") else None,
            "revenue_growth_yoy": round(safe_get(info, "revenueGrowth", 0) * 100, 2) if safe_get(info, "revenueGrowth") else None,

            # leverage
            "debt_to_equity": safe_get(info, "debtToEquity"),
            "interest_coverage": interest_coverage,
            "current_ratio": safe_get(info, "currentRatio"),
            "quick_ratio": safe_get(info, "quickRatio"),
            "total_debt": safe_get(info, "totalDebt"),
            "cash_and_equivalents": safe_get(info, "totalCash"),

            # ownership — needs screener.in, stored as NULL for now
            "promoter_holding": None,
            "promoter_holding_change": None,
            "pledged_percentage": None,
            "fii_holding": None,
            "dii_holding": None,

            # cashflow
            "free_cashflow": safe_get(info, "freeCashflow"),
            "operating_cashflow": safe_get(info, "operatingCashflow"),

            # analyst
            "analyst_target_price": safe_get(info, "targetMeanPrice"),
            "analyst_recommendation": safe_get(info, "recommendationKey"),
            "beta": safe_get(info, "beta"),

            "last_updated": datetime.now().isoformat()
        }
        return data

    except Exception as e:
        print(f"  Error fetching {ticker_symbol}: {e}")
        return None

def fetch_price_history(ticker_symbol, period="1y"):
    """
    Fetches daily OHLCV price data for the past 1 year
    period options: 1mo, 3mo, 6mo, 1y, 2y, 5y
    """
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period=period)

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
        print(f"  Error fetching price history for {ticker_symbol}: {e}")
        return []

def upsert_stock(data):
    """
    INSERT OR REPLACE — if ticker exists, update it
    if it doesn't exist yet, insert it
    """
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
    """
    INSERT OR IGNORE — skip if (ticker, date) already exists
    prevents duplicates if fetcher runs twice in a day
    """
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
    """
    Run this once to populate the database with all 20 stocks
    Called on startup from main.py
    """
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

    print(f"\nSeeding complete: {success}/{len(TICKERS)} stocks loaded")
    if failed:
        print(f"Failed: {failed}")

def refresh_prices():
    """
    Lightweight refresh — updates current price data only
    Called on a schedule to keep prices current
    """
    print("Refreshing prices...")
    for ticker in TICKERS:
        data = fetch_stock_data(ticker)
        if data:
            upsert_stock(data)
    print("Price refresh complete")
