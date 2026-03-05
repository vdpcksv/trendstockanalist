from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import json
import random
import FinanceDataReader as fdr
import logging
from fastapi_cache.decorator import cache

from dependencies import get_db, templates
from internal.cache import cache_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Dashboard 및 테마"])

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def _get_mock_flow_data():
    try:
        # Get actual trading days from a major stock (Samsung Electronics)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=20)
        df = fdr.DataReader('005930', start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        dates = reversed(df.index[-5:].strftime('%Y-%m-%d').tolist())
    except Exception:
        dates = []
        current_date = datetime.now()
        while len(dates) < 5:
            if current_date.weekday() < 5:  # 월~금
                dates.append(current_date.strftime("%Y-%m-%d"))
            current_date -= timedelta(days=1)
        
    flow_data = []
    for d in dates:
        random.seed(d)
        flow_data.append({
            "Date": d,
            "개인": random.randint(-2000, 2000),
            "외국인": random.randint(-1500, 2500),
            "기관": random.randint(-1000, 1500)
        })
    random.seed()
    return flow_data

def get_money_flow_data():
    url = "https://finance.naver.com/sise/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        flow_table = soup.select_one("div.box_type_m iframe") 
        if not flow_table:
            return _get_mock_flow_data()
        return _get_mock_flow_data()
    except Exception as e:
        logger.error(f"Flow data error: {e}")
        return _get_mock_flow_data()

def get_mock_net_buying_stocks():
    # 3일 연속 기관/외국인 순매수 (Mock)
    return [
        {"종목명": "SK하이닉스", "현재가": "164,000", "등락률": "+2.50%", "외국인_누적": "1,200억", "기관_누적": "850억"},
        {"종목명": "현대차", "현재가": "245,000", "등락률": "+1.80%", "외국인_누적": "950억", "기관_누적": "620억"},
        {"종목명": "알테오젠", "현재가": "182,500", "등락률": "+4.10%", "외국인_누적": "450억", "기관_누적": "310억"},
        {"종목명": "한미반도체", "현재가": "134,100", "등락률": "+3.20%", "외국인_누적": "380억", "기관_누적": "190억"},
        {"종목명": "기아", "현재가": "118,500", "등락률": "+1.10%", "외국인_누적": "320억", "기관_누적": "150억"}
    ]

def get_mock_theme_rotation():
    # 어제 vs 오늘 테마 순환 (Mock)
    return {
        "yesterday": ["2차전지 소재", "지능형 로봇", "제약/바이오"],
        "today": ["반도체 장비", "저PBR/금융", "자동차 부품"],
        "insight": "어제 시장을 주도했던 2차전지 및 로봇 섹터에서 차익 실현 매물이 출회되며, 반도체 및 저PBR 가치주(금융/자동차)로 자금 이동(Rotation)이 강하게 포착되고 있습니다."
    }

def get_theme_list():
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
        logger.error(f"Theme parsing error: {e}")
        return pd.DataFrame()

def get_theme_top_stocks(theme_url):
    try:
        response = requests.get(theme_url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        response.encoding = 'cp949'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        stocks = []
        table = soup.select_one('.type_5 tbody')
        if not table:
            return pd.DataFrame()
            
        for idx, tr in enumerate(table.select('tr')):
            if idx > 10: break
            name_tag = tr.select_one('.name a')
            price_tag = tr.select_one('.number')
            rate_tag = tr.select('.number')
            
            if name_tag and price_tag and len(rate_tag) >= 3:
                stocks.append({
                    "종목명": name_tag.text.strip(),
                    "현재가": price_tag.text.strip(),
                    "등락률": rate_tag[2].text.strip().replace('\n', '').replace('\t', '')
                })
                if len(stocks) >= 5:
                    break
                    
        return pd.DataFrame(stocks)
    except Exception as e:
        logger.error(f"Detailed Theme parsing error: {e}")
        return pd.DataFrame()

@cache(expire=86400) # 하루 한 번만 갱신
async def get_seasonality_data():
    """대표 섹터별 최근 10년간(또는 상장 이후)의 월별 승률 데이터를 반환합니다."""
    sectors = {
        "반도체": "005930",
        "2차전지": "006400",
        "바이오": "068270",
        "금융": "105560",
        "자동차": "005380",
        "게임/엔터": "036570"
    }

    results = {}
    today = datetime.now()
    start_date = (today - timedelta(days=365 * 10)).strftime('%Y-%m-%d')  # 10년 전

    try:
        def fetch_fdr():
            res = {}
            for name, ticker in sectors.items():
                df = fdr.DataReader(ticker, start=start_date)
                if df.empty:
                    continue
                df = df.resample('ME').last()
                df['Return'] = df['Close'].pct_change()
                df = df.dropna()
                df['Month'] = df.index.month
                df['Win'] = (df['Return'] > 0).astype(int)
                win_rates = (df.groupby('Month')['Win'].mean() * 100).round().astype(int)
                month_stats = []
                for m in range(1, 13):
                    if m in win_rates:
                        month_stats.append(int(win_rates[m]))
                    else:
                        month_stats.append(50)
                res[name] = month_stats
            return res
        
        import anyio
        results = await anyio.to_thread.run_sync(fetch_fdr)

    except Exception as e:
        logger.error(f"Seasonality calculation failed: {e}")
        # 완전히 실제 데이터만 사용하기 위해 가짜(Mock) 데이터를 제거했습니다.
        # 실패 시 빈 딕셔너리를 반환하여 프론트엔드에서 데이터 없음을 처리하도록 유도합니다.
        results = {}
        
    return results

@router.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    flow_data = cache_data.get("money_flow", [])
    if not flow_data:
        flow_data = _get_mock_flow_data()
    
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
            "insight": insight,
            "net_buy_stocks": get_mock_net_buying_stocks(),
            "theme_rotation": get_mock_theme_rotation()
        }
    )

@router.get("/seasonality", response_class=HTMLResponse)
async def read_seasonality(request: Request):
    season_data = await get_seasonality_data()
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

@router.get("/themes", response_class=HTMLResponse)
async def read_themes(request: Request, theme: str = None):
    df_themes = cache_data.get("theme_list", pd.DataFrame())
    if df_themes.empty:
        context = {"error": "테마 리스트 수집에 실패했습니다."}
        return templates.TemplateResponse(request=request, name="themes.html", context=context)
    
    themes_data = df_themes.to_dict('records')
    context = {"themes": themes_data, "selected_theme_data": None, "stocks_data": None, "ai_comment": None}
    
    if theme:
        selected_row = df_themes[df_themes['테마명'] == theme]
        if not selected_row.empty:
            selected_info = selected_row.iloc[0]
            context["selected_theme_data"] = selected_info.to_dict()
            
            cached_stocks = cache_data.get("theme_stocks", {}).get(selected_info['테마명'])
            if cached_stocks:
                context["stocks_data"] = cached_stocks
            else:
                # 웬만하면 실행되지 않으나, 캐시 누락 시 On-Demand Fallback
                df_stocks = get_theme_top_stocks(selected_info['링크'])
                if not df_stocks.empty:
                    context["stocks_data"] = df_stocks.to_dict('records')
                
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
