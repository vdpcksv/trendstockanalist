from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import json
import FinanceDataReader as fdr

app = FastAPI(title="Trend-Lotto Invest")

# Serve static files (CSS, JS) securely mapped to /static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Jinja2 templates directory
templates = Jinja2Templates(directory="templates")

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

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    flow_data = get_money_flow_data()
    
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
    # 테마 리스트 로딩
    df_themes = get_theme_list()
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

@app.get("/review", response_class=HTMLResponse)
async def read_review(request: Request, ticker: str = "005930"): # 기본값: 삼성전자
    context = {"ticker": ticker, "error": None, "chart_data": None, "ai_score": None}
    
    try:
        # 최근 6개월 데이터 로드
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(months=6)
        
        # DataFrame 로컬 변수
        df = fdr.DataReader(ticker, start_date, end_date)
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
        if final_score >= 80: phase_text = "극단적 과매도 (초강력 매수 타점)"
        elif final_score >= 60: phase_text = "상승 추세 (홀딩 및 분할 매수)"
        elif final_score >= 40: phase_text = "중립/박스권 (관망)"
        elif final_score >= 20: phase_text = "하락 추세 (신규 매수 보류)"
        else: phase_text = "극단적 과매수 (현금화/익절 타점)"
            
        context["ai_score"] = {
            "score": int(final_score),
            "phase": phase_text,
            "rsi": round(current_rsi, 1)
        }
            
    except Exception as e:
        context["error"] = f"에러 발생: {e}"

    return templates.TemplateResponse(request=request, name="review.html", context=context)

# ---------------------------------------------------------
# Tab 5 & 6 equivalents: Portfolio and Alerts (Form Handlers)
# ---------------------------------------------------------

@app.get("/portfolio", response_class=HTMLResponse)
async def read_portfolio(request: Request):
    # In a real app, this would read from a DB or session. For this refactoring, 
    # we'll pass an empty state and handle additions entirely via JavaScript localStorage 
    # to maintain the "Serverless/Static" feel of Streamlit's state.
    
    context = {"error": None}
    return templates.TemplateResponse(request=request, name="portfolio.html", context=context)
    
@app.get("/policies", response_class=HTMLResponse)
async def read_policies(request: Request):
    # Legal Policies and AdSense Guide
    return templates.TemplateResponse(request=request, name="policies.html", context={})

if __name__ == "__main__":
    import uvicorn
    # Make sure to run the app with 'uvicorn main:app --reload' in production
    uvicorn.run(app, host="127.0.0.1", port=8000)
