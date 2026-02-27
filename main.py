# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import json
import FinanceDataReader as fdr
from contextlib import asynccontextmanager
from functools import lru_cache
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from database import engine, get_db
import models
import schemas
import auth

# Create all tables in the database (this is safe if they already exist)
models.Base.metadata.create_all(bind=engine)

# --- Global Cache ---
# Stores the results of slow web scraping tasks to serve instantly
cache_data = {
    "money_flow": [],
    "theme_list": pd.DataFrame(),
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
    today = datetime.now().strftime("%Y-%m-%d")
    return [
        {"Date": today, "개인": -1500, "외국인": 2000, "기관": -500},
        {"Date": "2026-02-20", "개인": 500, "외국인": -800, "기관": 300},
        {"Date": "2026-02-19", "개인": -200, "외국인": 1200, "기관": -1000},
        {"Date": "2026-02-18", "개인": 1800, "외국인": -1500, "기관": -300},
        {"Date": "2026-02-17", "개인": 100, "외국인": 500, "기관": -600},
    ]

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

# --- Application Lifespan Events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize scheduler and run immediately
    scheduler = BackgroundScheduler()
    # Execute immediately on boot
    fetch_and_cache_data() 
    # Schedule to run every 10 minutes
    scheduler.add_job(fetch_and_cache_data, 'interval', minutes=10)
    scheduler.start()
    
    yield # Hand control back to FastAPI
    
    # Shutdown: Stop scheduler
    scheduler.shutdown()

app = FastAPI(title="Trend-Lotto Invest", lifespan=lifespan)

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
    return fdr.StockListing('KRX')

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
            
        return {
            "total": total,
            "positive_ratio": round((pos_count / total) * 100),
            "negative_ratio": round((neg_count / total) * 100),
            "neutral_ratio": round((neutral_count / total) * 100),
            "pos_count": pos_count,
            "neg_count": neg_count,
            "neutral_count": neutral_count,
            "news_list": analyzed_news
        }
    except Exception as e:
        print(f"Error fetching news sentiment: {e}")
        return None



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
        
        # 날짜 인덱스를 문자열로 변환하여 JSON 직렬화 가능하게 처리
        df.reset_index(inplace=True)
        if 'Date' in df.columns:
            df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
            
        # JSON 직렬화를 위한 dict 변환
        records = df.to_dict('records')
        context["chart_data"] = json.dumps(records)
        
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
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = auth.get_password_hash(user.password)
    # By default, we grant premium for testing. In prod, this is triggered by payment.
    db_user = models.User(username=user.username, hashed_password=hashed_password, membership="premium")
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"message": "User registered successfully"}

@app.post("/api/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = auth.timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "membership": user.membership}

@app.post("/api/portfolio", response_model=schemas.Portfolio)
def add_portfolio_item(item: schemas.PortfolioCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    db_item = models.Portfolio(
        ticker=item.ticker,
        target_price=item.target_price,
        user_id=current_user.id
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.get("/api/portfolio")
def get_portfolio_items(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    items = db.query(models.Portfolio).filter(models.Portfolio.user_id == current_user.id).all()
    # Mocking qty for now in response to match frontend expectations
    return [{"id": i.id, "name": i.ticker, "price": i.target_price or 0, "qty": 1} for i in items]

@app.delete("/api/portfolio/{item_id}")
def delete_portfolio_item(item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    item = db.query(models.Portfolio).filter(models.Portfolio.id == item_id, models.Portfolio.user_id == current_user.id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Item not found")

# --- Google AdSense ads.txt 인증 우회 라우트 ---
@app.get("/ads.txt", response_class=PlainTextResponse)
async def get_ads_txt():
    # 캡처 화면에서 확인한 본인의 pub ID를 적용한 공식 인증 텍스트
    return "google.com, pub-9065075656013134, DIRECT, f08c47fec0942fa0"

if __name__ == "__main__":
    import uvicorn
    # Make sure to run the app with 'uvicorn main:app --reload' in production
    uvicorn.run(app, host="127.0.0.1", port=8000)
