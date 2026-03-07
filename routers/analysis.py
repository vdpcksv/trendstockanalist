from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
import requests
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import FinanceDataReader as fdr
from functools import lru_cache
from fastapi_cache.decorator import cache

from dependencies import get_db, templates
from internal.cache import cache_data
import ai_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Analysis 및 매매복기"])

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

@lru_cache(maxsize=1)
def get_krx_stock_listing():
    return fdr.StockListing('KRX-DESC')

def resolve_ticker(query: str):
    query = query.strip()
    if query.isdigit() and len(query) == 6:
        return query
    try:
        df = get_krx_stock_listing()
        matches = df[df['Name'] == query]
        if not matches.empty:
            return matches.iloc[0]['Code']
    except Exception as e:
        logger.error(f"Error resolving ticker: {e}")
    return query

def get_stock_fundamentals(ticker: str):
    url = f"https://m.stock.naver.com/api/stock/{ticker}/finance/annual"
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.raise_for_status()
        data = res.json()
        headers = [item['title'] for item in data['financeInfo']['trTitleList']]
        parsed_data = {}
        target_indices = {
            0: "매출액", 1: "영업이익", 2: "당기순이익", 8: "부채비율", 7: "ROE(지배주주)", 12: "PER(배)", 14: "PBR(배)"
        }
        row_list = data['financeInfo']['rowList']
        header_keys = [item['key'] for item in data['financeInfo']['trTitleList']]
        for idx, key_name in target_indices.items():
            if idx < len(row_list):
                row = row_list[idx]
                vals = []
                for hk in header_keys:
                    vals.append(row['columns'].get(hk, {}).get('value', '-'))
                parsed_data[key_name] = vals
        return {"headers": headers, "data": parsed_data}
    except Exception as e:
        logger.error(f"Error fetching fundamentals: {e}")
        return None

def get_news_sentiment(ticker: str):
    ticker_name = ""
    # ticker가 숫자인지 확인하여 종목명을 가져오는 로직 (생략 시 그냥 ticker 사용)
    try:
        df = get_krx_stock_listing()
        matches = df[df['Code'] == ticker]
        if not matches.empty:
            ticker_name = matches.iloc[0]['Name']
    except:
        pass
    
    search_query = f"{ticker_name} 주식" if ticker_name else f"{ticker} 주식"
    import urllib.parse
    search_query_encoded = urllib.parse.quote(search_query)
    
    url = f"https://news.google.com/rss/search?q={search_query_encoded}&hl=ko&gl=KR&ceid=KR:ko"
    
    pos_keywords = ['상승', '급등', '돌파', '흑자', '수주', '호조', 'MOU', '강세', '체결', '최대', '신고가', '성장', '기대', '수혜', '반등']
    neg_keywords = ['하락', '급락', '적자', '우려', '수사', '악재', '약세', '신저가', '미달', '쇼크', '매도', '불안', '위기', '리스크']
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.raise_for_status()
        
        # Parse XML
        soup = BeautifulSoup(res.content, 'xml')
        items = soup.find_all('item')
        
        headlines = []
        for item in items[:15]:
            title = item.title.text if item.title else ''
            if title:
                if " - " in title:
                    title = " - ".join(title.split(" - ")[:-1])
                headlines.append(title)
                
        pos_count = neg_count = neutral_count = 0
        analyzed_news = []
        for title in headlines:
            is_pos = any(kw in title for kw in pos_keywords)
            is_neg = any(kw in title for kw in neg_keywords)
            if is_pos and not is_neg:
                sentiment = 'positive'
                pos_count += 1
            elif is_neg and not is_pos:
                sentiment = 'negative'
                neg_count += 1
            else:
                sentiment = 'neutral'
                neutral_count += 1
            analyzed_news.append({"title": title, "sentiment": sentiment})
        total = len(headlines)
        if total == 0: return None
        sentiment_order = {'positive': 0, 'neutral': 1, 'negative': 2}
        analyzed_news.sort(key=lambda x: sentiment_order.get(x['sentiment'], 3))
        
        llm_result = None
        cached_llm = cache_data["llm_sentiment"].get(ticker)
        if cached_llm and (datetime.now() - cached_llm['updated_at']).total_seconds() < 3600:
            llm_result = cached_llm['data']
        else:
            llm_result = ai_module.analyze_news_sentiment_with_llm(ticker, [news['title'] for news in analyzed_news])
            if llm_result:
                cache_data["llm_sentiment"][ticker] = {"data": llm_result, "updated_at": datetime.now()}
        return {
            "total": total, "positive_ratio": round((pos_count / total) * 100), "negative_ratio": round((neg_count / total) * 100),
            "neutral_ratio": round((neutral_count / total) * 100), "pos_count": pos_count, "neg_count": neg_count,
            "neutral_count": neutral_count, "news_list": analyzed_news, "llm_analysis": llm_result
        }
    except Exception as e:
        logger.error(f"Error fetching news sentiment: {e}")
        return None

def calculate_technical_indicators(df):
    df = df.copy()
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['MA120'] = df['Close'].rolling(window=120).mean()
    df['BB_MB'] = df['MA20']
    df['BB_STD'] = df['Close'].rolling(window=20).std()
    df['BB_UPPER'] = df['BB_MB'] + (df['BB_STD'] * 2)
    df['BB_LOWER'] = df['BB_MB'] - (df['BB_STD'] * 2)
    df['BB_UPPER_EXT'] = df['BB_MB'] + (df['BB_STD'] * 3)
    df['BB_LOWER_EXT'] = df['BB_MB'] - (df['BB_STD'] * 3)
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD Calculation
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    return df

@router.get("/api/search")
async def search_stocks(q: str = ""):
    if not q or len(q) < 1:
        return []
    try:
        df = get_krx_stock_listing()
        # Find stocks where name starts with query first, then those containing it
        starts_with = df[df['Name'].str.startswith(q, na=False)]
        contains = df[df['Name'].str.contains(q, na=False, case=False) & ~df['Name'].str.startswith(q, na=False)]
        matches = pd.concat([starts_with, contains])
        results = matches.head(10)[['Code', 'Name']].to_dict('records')
        return results
    except Exception as e:
        logger.error(f"Search API Error: {e}")
        return []

@router.get("/api/stock_seasonality/{ticker}")
@cache(expire=1800)
async def get_stock_seasonality(ticker: str):
    actual_ticker = resolve_ticker(ticker)
    try:
        def fetch_and_calc_seasonality(t: str):
            end_date = datetime.now()
            start_date = end_date - pd.DateOffset(years=10)
            df = fdr.DataReader(t, start_date, end_date)
            if df.empty:
                return {"status": "error", "message": "종목 데이터를 찾을 수 없습니다."}
            df['Year'] = df.index.year
            df['Month'] = df.index.month
            monthly_data = df.groupby(['Year', 'Month']).agg(Open=('Open', 'first'), Close=('Close', 'last')).reset_index()
            monthly_data['Return'] = (monthly_data['Close'] - monthly_data['Open']) / monthly_data['Open'] * 100
            seasonality = []
            for month in range(1, 13):
                month_data = monthly_data[monthly_data['Month'] == month]
                if month_data.empty:
                    seasonality.append({"Month": month, "WinRate": 0, "AvgReturn": 0})
                    continue
                total_years = len(month_data)
                win_years = len(month_data[month_data['Return'] > 0])
                win_rate = float((win_years / total_years) * 100)
                avg_return = float(month_data['Return'].mean() if not pd.isna(month_data['Return'].mean()) else 0.0)
                seasonality.append({"Month": month, "WinRate": round(win_rate, 1), "AvgReturn": round(avg_return, 2)})
            return {"status": "success", "data": seasonality}
        
        import asyncio
        result = await asyncio.to_thread(fetch_and_calc_seasonality, actual_ticker)
        if result.get("status") == "error":
            raise HTTPException(status_code=404, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Seasonality API Error: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/api/orderbook/{ticker}")
async def get_orderbook(ticker: str):
    try:
        actual_ticker = resolve_ticker(ticker)
        data = await kis_api.get_orderbook(actual_ticker)
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Orderbook error: {e}")
        return {"status": "error", "message": "호가 데이터를 불러오는데 실패했습니다 (API 연결 오류 또는 키 미설정)"}

@router.get("/ai-performance", response_class=HTMLResponse)
async def read_ai_performance(request: Request):
    # Mock data for AI performance report
    performance_data = {
        "accuracy": 78.5,
        "total_predictions": 1250,
        "successful_predictions": 981,
        "failed_predictions": 269,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "recent_hits": [
            {"ticker": "SK하이닉스", "date": "1주 전", "pred": "상승", "actual": "상승 (+8.2%)", "status": "hit"},
            {"ticker": "현대차", "date": "2주 전", "pred": "상승", "actual": "상승 (+5.1%)", "status": "hit"},
            {"ticker": "카카오", "date": "1개월 전", "pred": "하락", "actual": "하락 (-4.5%)", "status": "hit"},
            {"ticker": "NAVER", "date": "1개월 전", "pred": "상승", "actual": "하락 (-2.1%)", "status": "miss"},
        ]
    }
    return templates.TemplateResponse(request=request, name="ai_performance.html", context={"performance_data": performance_data})

@router.get("/review", response_class=HTMLResponse)
async def read_review(request: Request, ticker: str = "005930"):
    search_name = ticker.strip()
    actual_ticker = resolve_ticker(search_name)
    context = {"ticker": actual_ticker, "search_name": search_name, "error": None, "chart_data": None, "ai_score": None, "fundamentals": None, "sentiment_data": None}
    try:
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(years=1)
        df = fdr.DataReader(actual_ticker, start_date, end_date)
        if df.empty:
            context["error"] = "데이터를 불러올 수 없습니다. 종목 코드를 확인해 주세요."
            return templates.TemplateResponse(request=request, name="review.html", context=context)
        df = calculate_technical_indicators(df)
        df = df.dropna()
        # Only keep the last 6 months (approx 120 trading days) for chart rendering speed
        df = df.tail(120)
        df.reset_index(inplace=True)
        if 'Date' in df.columns: df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        records = df.to_dict('records')
        if not records:
            context["error"] = "기술적 지표 계산을 위한 충분한 과거 데이터가 없습니다."
            return templates.TemplateResponse(request=request, name="review.html", context=context)
        context["chart_data"] = json.dumps(records)
        
        forecast = cache_data["prophet_models"].get(actual_ticker)
        if not forecast:
            big_df = fdr.DataReader(actual_ticker, start_date - pd.DateOffset(years=2), end_date)
            forecast = ai_module.train_prophet_model(actual_ticker, big_df)
            if forecast: cache_data["prophet_models"][actual_ticker] = forecast
        context["prophet_forecast"] = json.dumps(forecast) if forecast else None

        last_row = df.iloc[-1]
        score = 50
        if last_row['MA5'] > last_row['MA20'] > last_row['MA60']: score += 20
        elif last_row['MA5'] < last_row['MA20'] < last_row['MA60']: score -= 20
            
        current_rsi = last_row['RSI']
        if current_rsi < 30: score += 15
        elif current_rsi > 70: score -= 15
        elif 40 <= current_rsi <= 60: score += 5
        
        current_price = last_row['Close']
        if current_price < last_row['BB_LOWER_EXT']: score += 25
        elif current_price < last_row['BB_LOWER']: score += 10
        elif current_price > last_row['BB_UPPER_EXT']: score -= 25
        elif current_price > last_row['BB_UPPER']: score -= 10
        elif current_price > last_row['MA5']: score += 5
            
        final_score = max(0, min(100, score))
        if final_score >= 80: phase_text = "극단적 과매도 (기술적 반등 가능성 구간)"
        elif final_score >= 60: phase_text = "상승 추세 (홀딩 및 분할 매수)"
        elif final_score >= 40: phase_text = "중립/박스권 (관망)"
        elif final_score >= 20: phase_text = "하락 추세 (신규 매수 보류)"
        else: phase_text = "극단적 과매수 (현금화/익절 타점)"
            
        context["ai_score"] = {"score": round(final_score), "phase": phase_text, "rsi": round(current_rsi, 2)}
        context["fundamentals"] = get_stock_fundamentals(actual_ticker)
        context["sentiment_data"] = get_news_sentiment(actual_ticker)
        return templates.TemplateResponse(request=request, name="review.html", context=context)
    except Exception as e:
        context["error"] = f"에러 발생: {e}"
        return templates.TemplateResponse(request=request, name="review.html", context=context)
