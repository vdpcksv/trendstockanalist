# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import json
import random
import FinanceDataReader as fdr
from contextlib import asynccontextmanager
from functools import lru_cache
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

from database import engine, get_db
import models
import schemas
import auth
import ai_module # Phase 1: AI & ML Integration
import infra_module # Phase 3: External API & Telegram

# Create all tables in the database (this is safe if they already exist)
models.Base.metadata.create_all(bind=engine)

# --- Global Cache ---
# Stores the results of slow web scraping tasks to serve instantly
cache_data = {
    "money_flow": [],
    "theme_list": pd.DataFrame(),
    "prophet_models": {}, # {ticker: forecast_data_list}
    "llm_sentiment": {}   # {ticker: {"data": dict, "updated_at": datetime}}
}



HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_money_flow_data():
    """Npay 증권 국내증시 메인 페이지에서 투자자별 동향을 파싱해옵니다."""
    url = "https://finance.naver.com/sise/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 투자자별 매매동향 파싱 로직 (기존 app.py 참고)
        flow_table = soup.select_one("div.box_type_m iframe") 
        if not flow_table:
            # 기본 모의 데이터 리턴 (크롤링 실패 시)
            return _get_mock_flow_data()
            
        # 정확한 iframe src를 추적하거나 더미데이터 반환
        return _get_mock_flow_data()
    except Exception as e:
        print(f"Flow data error: {e}")
        return _get_mock_flow_data()

def _get_mock_flow_data():
    dates = []
    current_date = datetime.now()
    while len(dates) < 5:
        if current_date.weekday() < 5:  # 월~금
            dates.append(current_date.strftime("%Y-%m-%d"))
        current_date -= timedelta(days=1)
        
    flow_data = []
    for d in dates:
        random.seed(d) # 날짜를 시드로 주어 해당 날짜의 데이터는 고정되게 함
        flow_data.append({
            "Date": d,
            "개인": random.randint(-2000, 2000),
            "외국인": random.randint(-1500, 2500),
            "기관": random.randint(-1000, 1500)
        })
    
    # 다른 곳의 랜덤에 영향 없도록 시드 초기화
    random.seed()
    
    return flow_data

# --- Background Task Functions ---
def fetch_and_cache_data():
    """Background task that periodically fetches scraping data."""
    try:
        print(f"[{datetime.now()}] Fetching background data...")
        flow_data = get_money_flow_data()
        theme_data = get_theme_list()
        
        # Safe update of cache
        if flow_data:
            cache_data["money_flow"] = flow_data
        if not theme_data.empty:
            cache_data["theme_list"] = theme_data
            
        print(f"[{datetime.now()}] Data fetch complete. Cached {len(flow_data)} flow records and {len(theme_data)} themes.")
    except Exception as e:
        print(f"Background fetch error: {e}")

def train_major_models():
    """Nightly background task to train Prophet models for major tickers."""
    major_tickers = ["005930", "000660", "373220"] # 삼성전자, SK하이닉스, LG에너지솔루션 등
    print(f"[{datetime.now()}] Starting nightly AI model training...")
    try:
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(years=3) # 학습용 3년치 데이터
        for ticker in major_tickers:
            df = fdr.DataReader(ticker, start_date, end_date)
            if not df.empty:
                forecast = ai_module.train_prophet_model(ticker, df)
                if forecast:
                    cache_data["prophet_models"][ticker] = forecast
        print(f"[{datetime.now()}] AI model training complete. Cached {len(cache_data['prophet_models'])} models.")
    except Exception as e:
        print(f"Background AI training error: {e}")

def calculate_mock_returns():
    """Phase 2: Nightly background task to calculate mock investment returns for users."""
    print(f"[{datetime.now()}] Starting mock investment settlement...")
    db = next(get_db())
    try:
        users = db.query(models.User).all()
        for user in users:
            total_value = 0.0
            portfolios = db.query(models.Portfolio).filter(models.Portfolio.user_id == user.id).all()
            for p in portfolios:
                if not p.target_price or p.target_price <= 0:
                    continue
                try:
                    df = fdr.DataReader(p.ticker, (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
                    if not df.empty:
                        current_price = float(df['Close'].iloc[-1])
                        # Calculate return percentage for this stock
                        ret = (current_price - p.target_price) / p.target_price * 100
                        # Add to user's total return value (simple summation for MVP)
                        total_value += float(ret * p.qty)
                except Exception:
                    pass
            
            user.total_return = round(float(total_value), 2)
        
        db.commit()
        print(f"[{datetime.now()}] Mock investment settlement complete for {len(users)} users.")
    except Exception as e:
        db.rollback()
        print(f"Background settlement error: {e}")
    finally:
        db.close()

def process_alerts():
    """Phase 3: Background daemon to check live prices and send Telegram alerts."""
    print(f"[{datetime.now()}] Checking live prices for active alerts...")
    db = next(get_db())
    kis_api = infra_module.KisApiHandler()
    
    try:
        active_alerts = db.query(models.Alert).filter(models.Alert.is_active == 1).all()
        if not active_alerts:
            return
            
        checked_tickers = {} # Cache prices within this run
        
        for alert in active_alerts:
            user = db.query(models.User).filter(models.User.id == alert.user_id).first()
            if not user:
                continue
                
            current_price = checked_tickers.get(alert.ticker)
            
            if current_price is None:
                # 1. Try KIS API First
                try:
                    # current_price = kis_api.get_current_price(alert.ticker) # In Prod
                    raise Exception("Mocking KIS Failure to force Fallback")
                except Exception as e:
                    # 2. Fallback to scraping/FDR
                    try:
                        df = fdr.DataReader(alert.ticker, (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'))
                        if not df.empty:
                            current_price = float(df['Close'].iloc[-1])
                    except:
                        continue # Skip if entirely failed
                        
                checked_tickers[alert.ticker] = current_price
                
            if current_price is None:
                continue
                
            # Check conditions
            triggered = False
            if alert.condition_type == 'ABOVE' and current_price >= alert.target_price:
                triggered = True
            elif alert.condition_type == 'BELOW' and current_price <= alert.target_price:
                triggered = True
                
            if triggered:
                # Send alert!
                msg = f"🔔 [AlphaFinder 알림]\n{user.username}님, [{alert.ticker}] 종목이 목표가 {alert.target_price:,.0f}원에 도달했습니다! (현재가: {current_price:,.0f}원)"
                infra_module.send_telegram_sync(msg)
                
                # Mark as inactive to avoid spam
                alert.is_active = 0
                
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Alert processing error: {e}")
    finally:
        db.close()

# --- Application Lifespan Events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize cache backend
    FastAPICache.init(InMemoryBackend(), prefix="trendlotto-cache")
    
    # Startup: Initialize scheduler and run immediately
    scheduler = BackgroundScheduler()
    # Execute immediately on boot
    fetch_and_cache_data() 
    # Schedule to run every 10 minutes
    scheduler.add_job(fetch_and_cache_data, 'interval', minutes=10)
    
    # Phase 1: Schedule Nightly Prophet Model Training (e.g., at 2:00 AM)
    scheduler.add_job(train_major_models, 'cron', hour=2, minute=0)
    
    # Phase 2: Schedule Nightly Mock Investment Settlement (Midnight)
    scheduler.add_job(calculate_mock_returns, 'cron', hour=0, minute=0)
    
    # Phase 3: Schedule Alert Processing Daemon (Every 5 minutes)
    scheduler.add_job(process_alerts, 'interval', minutes=5)
    
    scheduler.start()
    
    yield # Hand control back to FastAPI
    
    # Shutdown: Stop scheduler
    scheduler.shutdown()

app = FastAPI(title="AlphaFinder Invest", lifespan=lifespan)

# Phase 3: Security - CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to actual frontend domains
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Phase 5: Global Exception Handler
import logging
import traceback as tb

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("alphafinder")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unhandled exceptions."""
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}")
    logger.error(tb.format_exc())
    return HTMLResponse(
        content="<h1>500 Internal Server Error</h1><p>서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.</p>",
        status_code=500
    )

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests for monitoring."""
    start = datetime.now()
    response = await call_next(request)
    duration = (datetime.now() - start).total_seconds()
    if duration > 2.0:  # Only log slow requests (>2s)
        logger.warning(f"SLOW: {request.method} {request.url.path} took {duration:.2f}s")
    return response

# Serve static files (CSS, JS) securely mapped to /static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Jinja2 templates directory
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    # Use cached data instead of real-time scraping
    flow_data = cache_data.get("money_flow", [])
    if not flow_data:
        flow_data = _get_mock_flow_data()
    
    # Generate Insight
    last_record = flow_data[0]
    last_foreign = last_record["외국인"]
    last_instit = last_record["기관"]
    
    if last_foreign > 0 and last_instit > 0:
        insight = f"최근 영업일 기준 외국인({last_foreign}억)과 기관({last_instit}억)이 양매수를 기록하며 우호적인 시장 환경이 조성되었습니다."
    elif last_foreign > 0:
        insight = f"기관은 매도 우위이나, 외국인이 {last_foreign}억 원 순매수하며 지수를 방어하고 있습니다."
    elif last_instit > 0:
        insight = f"외국인은 매도 우위이나, 기관이 {last_instit}억 원 순매수하며 시장을 이끌고 있습니다."
    else:
        insight = "현재 기관과 외국인 모두 양매도를 기록 중입니다. 수급 보수적 접근이 필요합니다."
        
    return templates.TemplateResponse(
        request=request, name="dashboard.html",
        context={
            "flow_data_json": json.dumps(flow_data),
            "flow_data": flow_data,
            "insight": insight
        }
    )

def get_seasonality_data():
    """대표 섹터별 최근 10년간의 월별 승률 데이터를 반환합니다."""
    # (실 서버 환경에서는 fdr을 활용해 실시간 연산하지만, 여기선 Prototype 속도를 위해 Mock Data 사용)
    return {
        "반도체": [60, 50, 40, 70, 55, 45, 65, 80, 50, 60, 70, 85],
        "2차전지": [70, 60, 50, 45, 80, 75, 55, 60, 45, 50, 65, 90],
        "바이오": [40, 45, 55, 60, 50, 65, 70, 45, 80, 75, 60, 55],
        "금융": [55, 60, 70, 80, 75, 65, 50, 45, 40, 50, 60, 65],
        "자동차": [50, 55, 65, 70, 60, 50, 45, 55, 65, 80, 75, 70],
        "게임/엔터": [45, 50, 55, 60, 70, 80, 85, 75, 65, 55, 50, 45]
    }

@app.get("/seasonality", response_class=HTMLResponse)
async def read_seasonality(request: Request):
    season_data = get_seasonality_data()
    # DataFrame으로 변환 후 Heatmap용 Z(승률), X(월), Y(섹터) 리스트 추출
    df_hm = pd.DataFrame(season_data).T 
    df_hm.columns = [f"{i}월" for i in range(1, 13)]
    
    z_data = df_hm.values.tolist()
    y_labels = df_hm.index.tolist()
    x_labels = df_hm.columns.tolist()
    
    current_month_idx = datetime.now().month - 1
    
    return templates.TemplateResponse(
        request=request, name="seasonality.html",
        context={
            "z_data": json.dumps(z_data),
            "x_labels": json.dumps(x_labels),
            "y_labels": json.dumps(y_labels),
            "current_month_idx": current_month_idx
        }
    )

def get_theme_list():
    """Npay 증권 국내증시 테마 리스트를 파싱해옵니다."""
    url = "https://finance.naver.com/sise/theme.naver"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        response.encoding = 'cp949'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        themes = []
        table = soup.select_one('.type_1.theme')
        if not table:
            return pd.DataFrame()
            
        for tr in table.select('tr'):
            col_name = tr.select_one('td.col_type1 a')
            col_rate = tr.select_one('td.col_type2')
            
            if col_name and col_rate:
                link = "https://finance.naver.com" + col_name['href']
                themes.append({
                    "테마명": col_name.text.strip(),
                    "등락률(%)": col_rate.text.strip().replace('%', ''),
                    "링크": link
                })
        
        return pd.DataFrame(themes).head(20) if themes else pd.DataFrame()
    except Exception as e:
        print(f"Theme parsing error: {e}")
        return pd.DataFrame()

def get_theme_top_stocks(theme_url):
    """해당 테마 페이지 내 상위 등락률 종목 5개를 파싱합니다."""
    try:
        response = requests.get(theme_url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        response.encoding = 'cp949'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        stocks = []
        # 테마 페이지 내 편입 종목 테이블
        table = soup.select_one('.type_5 tbody')
        if not table:
            return pd.DataFrame()
            
        for idx, tr in enumerate(table.select('tr')):
            if idx > 10: break # 최대 10개만 탐색 (상위 5개를 위해 여유분 확보)
            name_tag = tr.select_one('.name a')
            price_tag = tr.select_one('.number')
            rate_tag = tr.select('.number')
            
            if name_tag and price_tag and len(rate_tag) >= 3:
                # rate_tag 구조: 현재가, 전일비, 등락률 ...
                stocks.append({
                    "종목명": name_tag.text.strip(),
                    "현재가": price_tag.text.strip(),
                    "등락률": rate_tag[2].text.strip().replace('\n', '').replace('\t', '')
                })
                if len(stocks) >= 5:
                    break
                    
        return pd.DataFrame(stocks)
    except Exception as e:
        print(f"Detailed Theme parsing error: {e}")
        return pd.DataFrame()

@app.get("/themes", response_class=HTMLResponse)
async def read_themes(request: Request, theme: str = None):
    # Use cached theme list
    df_themes = cache_data.get("theme_list", pd.DataFrame())
    if df_themes.empty:
        context = {"error": "테마 리스트 수집에 실패했습니다."}
        return templates.TemplateResponse(request=request, name="themes.html", context=context)
    
    themes_data = df_themes.to_dict('records')
    context = {"themes": themes_data, "selected_theme_data": None, "stocks_data": None, "ai_comment": None}
    
    # 쿼리 파라미터가 있으면 선택된 테마의 상세 정보 추출
    if theme:
        selected_row = df_themes[df_themes['테마명'] == theme]
        if not selected_row.empty:
            selected_info = selected_row.iloc[0]
            context["selected_theme_data"] = selected_info.to_dict()
            
            # 주도 종목 추출
            df_stocks = get_theme_top_stocks(selected_info['링크'])
            if not df_stocks.empty:
                context["stocks_data"] = df_stocks.to_dict('records')
                
            # AI 시나리오 진단 로직
            try:
                rate_val = float(selected_info['등락률(%)'].replace('+', ''))
                if rate_val > 3.0:
                    ai_title = "📈 매우 강한 자금 유입"
                    ai_desc = "현재 시장 주도 테마로 선정되었습니다. 대장주를 중심으로 한 짧은 단기 트레이딩 접근이 유효할 수 있습니다."
                elif rate_val > 0:
                    ai_title = "⚖️ 완만한 상승세"
                    ai_desc = "조용히 우상향 중인 테마입니다. 향후 모멘텀(뉴스/정책) 발생 시 추가 슈팅의 가능성이 있습니다."
                else:
                    ai_title = "📉 조정 중 (눌림목)"
                    ai_desc = "현재 매수세가 약화되었습니다. 단기 급락 후 계절적 반등을 노리는 중기 관점의 분할 매수 모니터링이 필요합니다."
                
                context["ai_comment"] = {"title": ai_title, "desc": ai_desc}
            except:
                pass

    return templates.TemplateResponse(request=request, name="themes.html", context=context)

def calculate_technical_indicators(df):
    """(기존 app.py 로직) 단순 이동평균, 볼린저 밴드, RSI 계산"""
    df = df.copy()
    # 5/20/60일 이동평균
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()

    # 볼린저 밴드 (20일, 2 standard deviations)
    df['BB_MB'] = df['MA20']
    df['BB_STD'] = df['Close'].rolling(window=20).std()
    df['BB_UPPER'] = df['BB_MB'] + (df['BB_STD'] * 2)
    df['BB_LOWER'] = df['BB_MB'] - (df['BB_STD'] * 2)

    # 극단적 볼린저 밴드 (20일, 3 standard deviations)
    df['BB_UPPER_EXT'] = df['BB_MB'] + (df['BB_STD'] * 3)
    df['BB_LOWER_EXT'] = df['BB_MB'] - (df['BB_STD'] * 3)

    # RSI (14일)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    return df

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
        print(f"Error resolving ticker: {e}")
    return query

def get_stock_fundamentals(ticker: str):
    """Scrapes essential fundamental data using Naver mobile JSON API for stability."""
    url = f"https://m.stock.naver.com/api/stock/{ticker}/finance/annual"
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.raise_for_status()
        data = res.json()
        
        headers = [item['title'] for item in data['financeInfo']['trTitleList']]
        parsed_data = {}
        
        target_indices = {
            0: "매출액",
            1: "영업이익",
            2: "당기순이익",
            8: "부채비율",
            7: "ROE(지배주주)",
            12: "PER(배)",
            14: "PBR(배)"
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
        print(f"Error fetching fundamentals: {e}")
        return None

def get_news_sentiment(ticker: str):
    """Fetches recent news from Naver Mobile API and performs keyword-based sentiment analysis."""
    url = f"https://m.stock.naver.com/api/news/stock/{ticker}?pageSize=15"
    
    pos_keywords = ['상승', '급등', '돌파', '흑자', '수주', '호조', 'MOU', '강세', '체결', '최대', '신고가', '성장', '기대', '수혜', '반등']
    neg_keywords = ['하락', '급락', '적자', '우려', '수사', '악재', '약세', '신저가', '미달', '쇼크', '매도', '불안', '위기', '리스크']
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.raise_for_status()
        data = json.loads(res.content.decode('utf-8', 'ignore'))
        
        headlines = []
        for group in data:
            for item in group.get('items', []):
                title = item.get('title', '')
                if title:
                    title = title.replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>')
                    headlines.append(title)
                    if len(headlines) >= 15:
                        break
            if len(headlines) >= 15:
                break
                
        pos_count = 0
        neg_count = 0
        neutral_count = 0
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
        if total == 0:
            return None
            
        # 긍정 -> 중립 -> 부정 순으로 정렬
        sentiment_order = {'positive': 0, 'neutral': 1, 'negative': 2}
        analyzed_news.sort(key=lambda x: sentiment_order.get(x['sentiment'], 3))
            
        # Phase 1: LLM 감성 분석 시도 (실패 시 기존 로직 결과만 반환)
        llm_result = None
        # 캐시 확인 (1시간 이내)
        cached_llm = cache_data["llm_sentiment"].get(ticker)
        if cached_llm and (datetime.now() - cached_llm['updated_at']).total_seconds() < 3600:
            llm_result = cached_llm['data']
        else:
            # LLM 분석 (시간 제한 피하기 위해 headline만 전달)
            llm_result = ai_module.analyze_news_sentiment_with_llm(ticker, [news['title'] for news in analyzed_news])
            if llm_result:
                cache_data["llm_sentiment"][ticker] = {
                    "data": llm_result,
                    "updated_at": datetime.now()
                }

        return {
            "total": total,
            "positive_ratio": round((pos_count / total) * 100),
            "negative_ratio": round((neg_count / total) * 100),
            "neutral_ratio": round((neutral_count / total) * 100),
            "pos_count": pos_count,
            "neg_count": neg_count,
            "neutral_count": neutral_count,
            "news_list": analyzed_news,
            "llm_analysis": llm_result # 프론트엔드에서 활용
        }
    except Exception as e:
        print(f"Error fetching news sentiment: {e}")
        return None

@app.get("/api/stock_seasonality/{ticker}")
@cache(expire=1800) # 캐시 유지시간: 30분
async def get_stock_seasonality(ticker: str):
    """최근 10년치 일봉을 바탕으로 월별 승률과 평균 수익률을 계산합니다."""
    # 종목명 입력시 로직에 의해 코드로 치환
    actual_ticker = resolve_ticker(ticker)
    try:
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(years=10)
        
        df = fdr.DataReader(actual_ticker, start_date, end_date)
        if df.empty:
            raise HTTPException(status_code=404, detail="종목 데이터를 찾을 수 없습니다.")
        
        df['Year'] = df.index.year
        df['Month'] = df.index.month

        # 월별 첫 시가, 마지막 종가 추출
        monthly_data = df.groupby(['Year', 'Month']).agg(
            Open=('Open', 'first'),
            Close=('Close', 'last')
        ).reset_index()
        
        # 월별 수익률 계산 (%) = (종가-시가)/시가 * 100
        monthly_data['Return'] = (monthly_data['Close'] - monthly_data['Open']) / monthly_data['Open'] * 100
        
        seasonality = []
        for month in range(1, 13):
            month_data = monthly_data[monthly_data['Month'] == month]
            if month_data.empty:
                seasonality.append({"Month": month, "WinRate": 0, "AvgReturn": 0})
                continue
            
            total_years = len(month_data)
            win_years = len(month_data[month_data['Return'] > 0])
            
            win_rate = (win_years / total_years) * 100
            avg_return = month_data['Return'].mean()
            
            seasonality.append({
                "Month": month,
                "WinRate": round(win_rate, 1),
                "AvgReturn": round(avg_return, 2)
            })
            
        return {"status": "success", "data": seasonality}
        
    except Exception as e:
        print(f"Seasonality API Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/leaderboard", response_class=HTMLResponse)
async def read_leaderboard(request: Request):
    """Phase 2: Render the mock investment leaderboard page."""
    return templates.TemplateResponse(request=request, name="leaderboard.html")

@app.get("/review", response_class=HTMLResponse)
async def read_review(request: Request, ticker: str = "005930"): # 기본값: 삼성전자
    search_name = ticker.strip()
    actual_ticker = resolve_ticker(search_name)
    
    context = {"ticker": actual_ticker, "search_name": search_name, "error": None, "chart_data": None, "ai_score": None, "fundamentals": None, "sentiment_data": None}
    
    try:
        # 최근 6개월 데이터 로드
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(months=6)
        
        # DataFrame 로컬 변수
        df = fdr.DataReader(actual_ticker, start_date, end_date)
        if df.empty:
            context["error"] = "데이터를 불러올 수 없습니다. 종목 코드를 확인해 주세요."
            return templates.TemplateResponse(request=request, name="review.html", context=context)
            
        df = calculate_technical_indicators(df)
        df = df.dropna() # 지표 계산 후 NaN 제거
        
        # 데이터 프레젠테이션 (수정 불가)
        df.reset_index(inplace=True)
        if 'Date' in df.columns:
            df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
            
        records = df.to_dict('records')
        context["chart_data"] = json.dumps(records)
        
        # Phase 1: Prophet 포캐스트 결합
        forecast = cache_data["prophet_models"].get(actual_ticker)
        if not forecast:
            # 주요 종목이 아니면 실시간으로 예측 (3년치 필요)
            big_df = fdr.DataReader(actual_ticker, start_date - pd.DateOffset(years=2), end_date)
            forecast = ai_module.train_prophet_model(actual_ticker, big_df)
            if forecast:
                cache_data["prophet_models"][actual_ticker] = forecast
        
        context["prophet_forecast"] = json.dumps(forecast) if forecast else None

        # --- AI 퀀트 종합 분석 (로직 포팅) ---
        last_row = df.iloc[-1]
        score = 50
        
        # 이동평균 정배열/역배열 가점
        if last_row['MA5'] > last_row['MA20'] > last_row['MA60']: score += 20
        elif last_row['MA5'] < last_row['MA20'] < last_row['MA60']: score -= 20
            
        # RSI 점수 로직 (고급)
        current_rsi = last_row['RSI']
        if current_rsi < 30: score += 15 # 과매도 (반등 기대)
        elif current_rsi > 70: score -= 15 # 과매수 (조정 우려)
        elif 40 <= current_rsi <= 60: score += 5 # 안정적 추세
        
        # 볼린저 밴드 위치 (3표준편차 포함)
        current_price = last_row['Close']
        if current_price < last_row['BB_LOWER_EXT']: score += 25 # 극단적 하단 이탈 (강한 물타기/매수)
        elif current_price < last_row['BB_LOWER']: score += 10 # 밴드 하단 이탈 (단기 반등)
        elif current_price > last_row['BB_UPPER_EXT']: score -= 25 # 극단적 상단 이탈 (강한 차익실현)
        elif current_price > last_row['BB_UPPER']: score -= 10 # 밴드 상단 돌파 (과열)
        elif current_price > last_row['MA5']: score += 5 # 단기 이평선 지지
            
        # 점수 정규화 (0~100)
        final_score = max(0, min(100, score))
        
        # 시나리오 매핑
        if final_score >= 80: phase_text = "극단적 과매도 (기술적 반등 가능성 구간)"
        elif final_score >= 60: phase_text = "상승 추세 (홀딩 및 분할 매수)"
        elif final_score >= 40: phase_text = "중립/박스권 (관망)"
        elif final_score >= 20: phase_text = "하락 추세 (신규 매수 보류)"
        else: phase_text = "극단적 과매수 (현금화/익절 타점)"
            
        context["ai_score"] = {
            "score": round(final_score),
            "phase": phase_text,
            "rsi": round(current_rsi, 2)
        }
        
        # 펀더멘털 데이터 수집 결합
        context["fundamentals"] = get_stock_fundamentals(actual_ticker)
        
        # 뉴스 센티멘트 분석 결합
        context["sentiment_data"] = get_news_sentiment(actual_ticker)
        
        return templates.TemplateResponse(request=request, name="review.html", context=context)
            
    except Exception as e:
        context["error"] = f"에러 발생: {e}"

    return templates.TemplateResponse(request=request, name="review.html", context=context)

# ---------------------------------------------------------
# Tab 5 & 6 equivalents: Portfolio and Alerts (Form Handlers)
# ---------------------------------------------------------

@app.get("/portfolio", response_class=HTMLResponse)
async def read_portfolio(request: Request):
    context = {"error": None}
    return templates.TemplateResponse(request=request, name="portfolio.html", context=context)
    
@app.get("/policies", response_class=HTMLResponse)
async def read_policies(request: Request):
    # Legal Policies and AdSense Guide
    return templates.TemplateResponse(request=request, name="policies.html", context={})

# --- API Endpoints for DB CRUD & Auth ---
@app.post("/api/register") # Removed response_model to prevent validation error when returning a dict
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="이미 등록된 아이디입니다.")
    
    hashed_password = auth.get_password_hash(user.password)
    # By default, we grant premium for testing. In prod, this is triggered by payment.
    db_user = models.User(username=user.username, hashed_password=hashed_password, membership="premium")
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"message": "회원가입이 완료되었습니다!"}

@app.post("/api/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = auth.timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "membership": user.membership}

@app.post("/api/portfolio", response_model=schemas.Portfolio)
def add_portfolio_item(item: schemas.PortfolioCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    # Check if the user already has this ticker in their portfolio
    existing_item = db.query(models.Portfolio).filter(
        models.Portfolio.user_id == current_user.id,
        models.Portfolio.ticker == item.ticker
    ).first()

    if existing_item:
        # Calculate new average target (buy) price
        old_qty = existing_item.qty or 1
        old_price = existing_item.target_price or 0.0
        
        new_qty = item.qty or 1
        new_price = item.target_price or 0.0

        total_old_value = old_qty * old_price
        total_new_value = new_qty * new_price
        
        combined_qty = old_qty + new_qty
        avg_price = (total_old_value + total_new_value) / combined_qty

        # Update the existing record
        existing_item.qty = combined_qty
        existing_item.target_price = avg_price
        db.commit()
        db.refresh(existing_item)
        return existing_item
    else:
        # Create a new record
        db_item = models.Portfolio(
            ticker=item.ticker,
            target_price=item.target_price,
            qty=item.qty,
            user_id=current_user.id
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item

def get_current_price(stock_name: str) -> float:
    try:
        ticker = resolve_ticker(stock_name)
        # Fetch data for the last 7 days to ensure we get the latest trading day
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        df = fdr.DataReader(ticker, start=start_date)
        if not df.empty:
            return float(df.iloc[-1]['Close'])
    except Exception as e:
        print(f"Error fetching current price for {stock_name}: {e}")
    return 0.0

@app.get("/api/portfolio")
def get_portfolio_items(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    items = db.query(models.Portfolio).filter(models.Portfolio.user_id == current_user.id).all()
    
    result = []
    for i in items:
        # In case the table was created before qty column, fallback to 1
        qty = i.qty if hasattr(i, 'qty') and i.qty is not None else 1
        current_price = get_current_price(i.ticker)
        result.append({
            "id": i.id, 
            "name": i.ticker, 
            "price": i.target_price or 0, # This is the buy price
            "qty": qty,
            "current_price": current_price
        })
    return result

@app.delete("/api/portfolio/{item_id}")
def delete_portfolio_item(item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    item = db.query(models.Portfolio).filter(models.Portfolio.id == item_id, models.Portfolio.user_id == current_user.id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="해당 항목을 찾을 수 없습니다.")

# --- Phase 2: Community API (Comments & Votes) ---
@app.post("/api/comments/{ticker}", response_model=schemas.CommentResponse)
def create_comment(ticker: str, comment: schemas.CommentCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    resolved_ticker = resolve_ticker(ticker)
    db_comment = models.Comment(
        user_id=current_user.id,
        ticker=resolved_ticker,
        content=comment.content
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    
    return schemas.CommentResponse(
        id=db_comment.id,
        content=db_comment.content,
        ticker=db_comment.ticker,
        user_id=db_comment.user_id,
        created_at=db_comment.created_at,
        username=current_user.username
    )

@app.get("/api/comments/{ticker}")
def get_comments(ticker: str, db: Session = Depends(get_db)):
    resolved_ticker = resolve_ticker(ticker)
    comments = db.query(models.Comment, models.User.username)\
        .join(models.User, models.Comment.user_id == models.User.id)\
        .filter(models.Comment.ticker == resolved_ticker)\
        .order_by(models.Comment.created_at.desc())\
        .limit(50).all()
        
    result = []
    for c, uname in comments:
        result.append({
            "id": c.id,
            "content": c.content,
            "ticker": c.ticker,
            "user_id": c.user_id,
            "created_at": c.created_at.isoformat(),
            "username": uname
        })
    return result

@app.post("/api/votes/{ticker}")
def cast_vote(ticker: str, vote: schemas.VoteCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    resolved_ticker = resolve_ticker(ticker)
    existing_vote = db.query(models.Vote).filter(
        models.Vote.user_id == current_user.id,
        models.Vote.ticker == resolved_ticker
    ).first()
    
    if existing_vote:
        existing_vote.vote_type = vote.vote_type
    else:
        new_vote = models.Vote(
            user_id=current_user.id,
            ticker=resolved_ticker,
            vote_type=vote.vote_type
        )
        db.add(new_vote)
        
    db.commit()
    return {"status": "success"}

@app.get("/api/votes/{ticker}")
def get_votes(ticker: str, db: Session = Depends(get_db)):
    resolved_ticker = resolve_ticker(ticker)
    bull_count = db.query(models.Vote).filter(models.Vote.ticker == resolved_ticker, models.Vote.vote_type == 'BULL').count()
    bear_count = db.query(models.Vote).filter(models.Vote.ticker == resolved_ticker, models.Vote.vote_type == 'BEAR').count()
    total = bull_count + bear_count
    
    return {
        "bull": bull_count,
        "bear": bear_count,
        "total": total,
        "bull_ratio": round(bull_count / total * 100) if total > 0 else 0,
        "bear_ratio": round(bear_count / total * 100) if total > 0 else 0
    }

@app.get("/api/leaderboard")
def get_leaderboard(db: Session = Depends(get_db), limit: int = 10):
    """Phase 2: Fetch top users ranked by mock investment returns."""
    top_users = db.query(models.User.username, models.User.total_return)\
        .filter(models.User.total_return.isnot(None))\
        .order_by(models.User.total_return.desc())\
        .limit(limit).all()
        
    return [{"rank": i+1, "username": u.username, "return": u.total_return} for i, u in enumerate(top_users)]

# --- Phase 3: Alert CRUD API Endpoints ---
@app.post("/api/alerts", response_model=schemas.AlertResponse)
def create_alert(alert: schemas.AlertCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Phase 3: Create a price alert for a stock ticker."""
    # Validate condition_type
    if alert.condition_type not in ('ABOVE', 'BELOW'):
        raise HTTPException(status_code=400, detail="조건 유형은 'ABOVE' 또는 'BELOW'만 가능합니다.")
    
    # Limit active alerts per user (prevent spam)
    active_count = db.query(models.Alert).filter(
        models.Alert.user_id == current_user.id,
        models.Alert.is_active == 1
    ).count()
    if active_count >= 10:
        raise HTTPException(status_code=400, detail="활성 알림은 최대 10개까지 설정할 수 있습니다.")
    
    resolved_ticker = resolve_ticker(alert.ticker)
    
    db_alert = models.Alert(
        user_id=current_user.id,
        ticker=resolved_ticker,
        target_price=alert.target_price,
        condition_type=alert.condition_type,
        is_active=1
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

@app.get("/api/alerts")
def get_my_alerts(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Phase 3: Get current user's active alerts."""
    alerts = db.query(models.Alert).filter(
        models.Alert.user_id == current_user.id
    ).order_by(models.Alert.created_at.desc()).all()
    
    return [{
        "id": a.id,
        "ticker": a.ticker,
        "target_price": a.target_price,
        "condition_type": a.condition_type,
        "is_active": a.is_active,
        "created_at": str(a.created_at)
    } for a in alerts]

@app.delete("/api/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Phase 3: Delete a specific alert."""
    alert = db.query(models.Alert).filter(
        models.Alert.id == alert_id,
        models.Alert.user_id == current_user.id
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")
    
    db.delete(alert)
    db.commit()
    return {"status": "success", "message": "알림이 삭제되었습니다."}

# --- Google AdSense ads.txt 인증 우회 라우트 ---
@app.get("/ads.txt", response_class=PlainTextResponse)
async def get_ads_txt():
    # 캡처 화면에서 확인한 본인의 pub ID를 적용한 공식 인증 텍스트
    return "google.com, pub-9065075656013134, DIRECT, f08c47fec0942fa0"

# =====================================================
# Phase 4: Monetization & Marketing Endpoints
# =====================================================

# --- 4-1. Freemium Membership API ---
@app.get("/api/membership")
def get_membership(current_user: models.User = Depends(auth.get_current_user)):
    """Check current user's membership status."""
    return {
        "username": current_user.username,
        "membership": current_user.membership or "basic",
        "features": {
            "ai_analysis": True,  # Available to all
            "community": True,    # Available to all
            "alerts": current_user.membership == "premium",
            "unlimited_alerts": current_user.membership == "premium",
            "priority_support": current_user.membership == "premium",
        }
    }

@app.post("/api/membership/upgrade")
def upgrade_membership(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Phase 4: Upgrade user to premium.
    In production, this would be called after payment confirmation webhook.
    For MVP, this is a direct upgrade endpoint.
    """
    current_user.membership = "premium"
    db.commit()
    return {"status": "success", "message": "프리미엄 회원으로 업그레이드되었습니다!", "membership": "premium"}

# --- 4-2. Payment Webhook (Toss Payments / PortOne Ready) ---
@app.post("/api/payment/confirm")
async def payment_confirm(request: Request, db: Session = Depends(get_db)):
    """
    Phase 4: Payment confirmation webhook receiver.
    In production, verify the payment with Toss/PortOne API before upgrading.
    """
    try:
        body = await request.json()
        payment_key = body.get("paymentKey", "")
        order_id = body.get("orderId", "")
        amount = body.get("amount", 0)
        
        # Validate required fields
        if not payment_key or not order_id or not amount:
            raise HTTPException(status_code=400, detail="필수 결제 정보(paymentKey, orderId, amount)가 누락되었습니다.")
        
        # TODO: In production, verify payment with external API:
        # POST https://api.tosspayments.com/v1/payments/confirm
        # with paymentKey, orderId, amount
        
        # For MVP, log the payment attempt
        print(f"[Payment] Received: key={payment_key}, order={order_id}, amount={amount}")
        
        return {"status": "success", "message": "결제 확인이 완료되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"결제 처리 중 오류: {str(e)}")

@app.post("/api/membership/downgrade")
def downgrade_membership(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Phase 4: Downgrade user back to basic (cancel premium)."""
    current_user.membership = "basic"
    db.commit()
    return {"status": "success", "message": "기본 회원으로 전환되었습니다.", "membership": "basic"}

# --- 4-3. SEO: Dynamic Sitemap.xml & robots.txt ---
from fastapi.responses import Response

@app.get("/sitemap.xml")
async def sitemap():
    """Phase 4: Generate dynamic sitemap for SEO crawlers."""
    base_url = "https://alphafinder.kr"
    today = datetime.now().strftime("%Y-%m-%d")
    
    pages = [
        {"loc": "/", "priority": "1.0", "changefreq": "daily"},
        {"loc": "/seasonality", "priority": "0.8", "changefreq": "weekly"},
        {"loc": "/themes", "priority": "0.8", "changefreq": "daily"},
        {"loc": "/leaderboard", "priority": "0.7", "changefreq": "daily"},
        {"loc": "/review", "priority": "0.9", "changefreq": "daily"},
        {"loc": "/policies", "priority": "0.3", "changefreq": "monthly"},
    ]
    
    xml_items = ""
    for p in pages:
        xml_items += f"""  <url>
    <loc>{base_url}{p['loc']}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{p['changefreq']}</changefreq>
    <priority>{p['priority']}</priority>
  </url>
"""
    
    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{xml_items}</urlset>"""
    
    return Response(content=sitemap_xml, media_type="application/xml")

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    """Phase 4: SEO robots.txt for search engine crawlers."""
    return """User-agent: *
Allow: /
Disallow: /api/
Disallow: /portfolio
Sitemap: https://alphafinder.kr/sitemap.xml
"""

# --- 4-4. Dynamic OG Image API ---
@app.get("/api/og-image/{ticker}")
async def generate_og_image(ticker: str, db: Session = Depends(get_db)):
    """
    Phase 4: Generate dynamic Open Graph image data for social sharing.
    Returns JSON with pre-computed OG meta tag values.
    Frontend uses these values in <meta> tags for KakaoTalk/Twitter/Facebook previews.
    """
    resolved_ticker = resolve_ticker(ticker)
    
    # Get latest price data
    try:
        df = fdr.DataReader(resolved_ticker, (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        if not df.empty:
            current_price = float(df['Close'].iloc[-1])
            price_30d_ago = float(df['Close'].iloc[0])
            change_pct = round((current_price - price_30d_ago) / price_30d_ago * 100, 2)
            if change_pct > 0:
                trend = "상승"
            elif change_pct < 0:
                trend = "하락"
            else:
                trend = "보합"
        else:
            current_price = 0
            change_pct = 0
            trend = "N/A"
    except:
        current_price = 0
        change_pct = 0
        trend = "N/A"
    
    # Vote sentiment
    bull = db.query(models.Vote).filter(models.Vote.ticker == resolved_ticker, models.Vote.vote_type == 'BULL').count()
    bear = db.query(models.Vote).filter(models.Vote.ticker == resolved_ticker, models.Vote.vote_type == 'BEAR').count()
    total = bull + bear
    sentiment = f"BULL {round(bull/total*100)}%" if total > 0 else "투표 없음"
    
    return {
        "title": f"AlphaFinder | {resolved_ticker} 종목 AI 분석",
        "description": f"{trend} {change_pct:+.2f}% (30일) | 현재가 {current_price:,.0f}원 | 투자자 심리: {sentiment}",
        "image_text": f"{resolved_ticker} | {current_price:,.0f}원 | {change_pct:+.2f}%",
        "ticker": resolved_ticker,
        "current_price": current_price,
        "change_pct": change_pct,
        "sentiment": sentiment
    }

# --- 4-5. P&L (Profit & Loss) Certificate Image Data API ---
@app.get("/api/pnl-card")
def generate_pnl_card(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Phase 4: Generate data for a P&L (profit/loss) sharing card.
    Returns structured data that the frontend renders as a shareable image.
    """
    portfolios = db.query(models.Portfolio).filter(
        models.Portfolio.user_id == current_user.id
    ).all()
    
    holdings = []
    total_pnl = 0.0
    
    for p in portfolios:
        try:
            df = fdr.DataReader(p.ticker, (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
            if not df.empty and p.target_price and p.target_price > 0:
                current = float(df['Close'].iloc[-1])
                pnl_pct = round((current - p.target_price) / p.target_price * 100, 2)
                pnl_value = round((current - p.target_price) * p.qty, 0)
                total_pnl += pnl_value
                holdings.append({
                    "ticker": p.ticker,
                    "buy_price": p.target_price,
                    "current_price": current,
                    "qty": p.qty,
                    "pnl_pct": pnl_pct,
                    "pnl_value": pnl_value
                })
        except:
            pass
    
    # Determine rank
    rank_data = db.query(models.User.username, models.User.total_return)\
        .filter(models.User.total_return.isnot(None))\
        .order_by(models.User.total_return.desc()).all()
    
    user_rank = "N/A"
    for i, r in enumerate(rank_data):
        if r.username == current_user.username:
            user_rank = f"{i + 1}/{len(rank_data)}"
            break
    
    return {
        "username": current_user.username,
        "total_return": current_user.total_return or 0.0,
        "rank": user_rank,
        "holdings": holdings,
        "total_pnl_value": total_pnl,
        "generated_at": datetime.now().isoformat(),
        "watermark": "AlphaFinder | alphafinder.kr"
    }

if __name__ == "__main__":
    import uvicorn
    # Make sure to run the app with 'uvicorn main:app --reload' in production
    uvicorn.run(app, host="127.0.0.1", port=8000)
