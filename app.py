import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import random
import time
import FinanceDataReader as fdr

# ==========================================
# 1. 네이버 금융 데이터 크롤링 헬퍼 함수
# ==========================================
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

@st.cache_data(ttl=600) # 10분 캐싱
def get_kospi_investor_trend():
    """네이버 금융 - KOSPI 투자매매 동향 크롤링 (최근 15일치 추이)"""
    today_str = datetime.now().strftime('%Y%m%d')
    url = f"https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={today_str}&mktType=KOSPI&page=1"
    res = requests.get(url, headers=headers)
    res.encoding = 'euc-kr' # 해결: 한글 깨짐 및 데이터 누락 방지
    soup = BeautifulSoup(res.text, 'html.parser')
    
    dates = []
    retail = [] # 개인
    foreign = [] # 외국인
    instit = [] # 기관
    
    table = soup.find('table', {'class': 'type_1'})
    if not table: return pd.DataFrame()
    rows = table.find_all('tr')
    
    for row in rows:
        cols = row.find_all('td')
        # 해결: 네이버 금융 일별매매동향 실제 컬럼 수는 11개임
        if len(cols) == 11 and cols[0].text.strip().replace('.', '').isdigit():
            date_str = cols[0].text.strip()
            
            def parse_num(txt):
                # 콤마 제거 후 정수 변환 (데이터가 없을 경우 예외처리)
                try:
                    return int(txt.replace(',', '').strip())
                except:
                    return 0
            
            r_val = parse_num(cols[1].text)
            f_val = parse_num(cols[2].text)
            i_val = parse_num(cols[3].text)
            
            dates.append(date_str)
            retail.append(r_val)
            foreign.append(f_val)
            instit.append(i_val)
            
            if len(dates) >= 15: # 15일치만
                break
                
    df = pd.DataFrame({
        'Date': dates,
        '개인': retail,
        '외국인': foreign,
        '기관': instit
    })
    
    if df.empty: return df
    
    # 과거 날짜순 정렬
    df = df.iloc[::-1].reset_index(drop=True)
    return df

@st.cache_data(ttl=3600)
def get_theme_list():
    """네이버 주요 테마 최근 등락률 상위 크롤링"""
    url = "https://finance.naver.com/sise/theme.naver"
    res = requests.get(url, headers=headers)
    res.encoding = 'euc-kr'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    themes = []
    rows = soup.find_all('tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 3 and cols[0].find('a'):
            theme_name = cols[0].find('a').text.strip()
            theme_link = "https://finance.naver.com" + cols[0].find('a')['href']
            
            # 전일대비 등락률 텍스트 처리
            rate_text = cols[1].text.strip()
            # 상승/하락 기호 변환
            if rate_text.startswith('+'):
                 rate_val = float(rate_text.replace('+', '').replace('%', ''))
            elif rate_text.startswith('-'):
                 rate_val = float(rate_text.replace('-', '-').replace('%', ''))
            else:
                 rate_val = 0.0

            themes.append({
                '테마명': theme_name,
                '등락률(%)': rate_val,
                '링크': theme_link
            })
            
            if len(themes) >= 20: # 상위 20개만
                break
    return pd.DataFrame(themes)

@st.cache_data(ttl=600)
def get_theme_top_stocks(theme_url):
    """특정 테마 페이지 진입하여 속한 종목들 크롤링"""
    res = requests.get(theme_url, headers=headers)
    res.encoding = 'euc-kr'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    stocks = []
    # 테마 속 종목 테이블
    table = soup.find('table', {'class': 'type_5'})
    if not table: return pd.DataFrame()
    rows = table.find_all('tr')
    
    for row in rows:
        tds = row.find_all('td')
        if len(tds) >= 3 and tds[0].find('a'):
            name = tds[0].find('a').text.strip()
            # 현재가
            price = tds[1].text.strip()
            # 등락률 (전일비)
            rate_node = tds[2]
            rate_text = rate_node.text.strip().replace('\n', '')
            
            stocks.append({
                '종목명': name,
                '현재가': price,
                '등락률': rate_text
            })
            if len(stocks) >= 5: # 주요 5종목만
                break
    return pd.DataFrame(stocks)


@st.cache_data(ttl=86400) # 과거 데이터라 하루에 한 번만 갱신(캐싱)
def get_seasonality_data():
    """대표 섹터 종목들의 최근 10년 월별 승률(상승 마감 확률) 계산"""
    # 대표 섹터 및 대장주 종목코드
    symbols = {
        '반도체(삼성전자)': '005930',
        '바이오(삼성바이오)': '207940',
        '2차전지(LG엔솔)': '373220', # 상장일이 짧을 수 있음
        '자동차(현대차)': '005380',
        '인터넷(NAVER)': '035420'
    }
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 10) # 10년 전
    
    heatmap_dict = {}
    
    for name, ticker in symbols.items():
        try:
            # 1. 10년 치 주가 데이터 가져오기
            df = fdr.DataReader(ticker, start_date, end_date)
            if df.empty: continue
            
            # 2. 월말 종가 기준으로 수익률 계산
            df_monthly = df['Close'].resample('ME').last() # pandas 최신 버전 반영 ('M' -> 'ME')
            returns = df_monthly.pct_change() * 100
            
            # 3. 데이터프레임 변환 후 '월' 추출
            df_ret = returns.reset_index()
            df_ret.columns = ['Date', 'Return']
            df_ret['Month'] = df_ret['Date'].dt.month
            
            # 4. 월별 승률 계산 (수익률이 0보다 큰 달의 비율)
            win_rates = []
            for m in range(1, 13):
                month_data = df_ret[df_ret['Month'] == m]['Return'].dropna()
                if len(month_data) == 0:
                    win_rates.append(0)
                else:
                    win_rate = (month_data > 0).sum() / len(month_data) * 100
                    win_rates.append(round(win_rate, 1))
                    
            heatmap_dict[name] = win_rates
        except Exception as e:
            pass
            
    return heatmap_dict

# ==========================================
# 2. UI 구성 (Streamlit)
# ==========================================

st.set_page_config(
    page_title="Trend-Lotto Invest",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3256/3256424.png", width=100) 
    st.title("Trend-Lotto Invest")
    st.markdown("---")
    st.write("초개인화된 스마트 트렌드 추적 & 자금 흐름 분석 플랫폼 (Naver 연동)")
    
    st.markdown("### 주요 기능")
    st.info("💡 **자금 흐름 (Money Flow)**\n네이버 금융 KOSPI 15일 누적 수급 추적")
    st.success("🗓️ **계절성 (Seasonality)**\n장기 시점 주요 테마 상승/하락 섹터 분석")
    st.warning("🎯 **초개인화 시나리오**\n실시간 테마별 대장주 현황 및 인사이트 제공")

st.title("📈 Trend-Lotto Invest Prototype (Real Data)")
st.markdown("네이버 금융(Naver Finance)의 실시간 지표를 크롤링하여 트렌드를 추적합니다.")

tab1, tab2, tab3 = st.tabs(["💰 실시간 자금 흐름", "🗓️ 계절성 트렌드(Mock+Real)", "🎯 테마별 맞춤형 시나리오"])

# --- Tab 1: 자금 흐름 (Money Flow) ---
with tab1:
    st.header("KOSPI 기관 및 외국인 수급 동향")
    st.markdown("네이버 금융 [투자자별 매매동향] 메뉴에서 최근 영업일 기준 데이터를 집계했습니다.")
    
    with st.spinner("네이버 금융 수급 데이터를 불러오는 중..."):
        df_flow = get_kospi_investor_trend()
    
    if not df_flow.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("외국인/기관 순매수 추이 (단위: 억 원)")
            fig_net_buy = go.Figure()
            # 순매수 막대 그래프 (0 기준 위/아래)
            fig_net_buy.add_trace(go.Bar(x=df_flow['Date'], y=df_flow['기관'], name='기관', marker_color='#3b82f6'))
            fig_net_buy.add_trace(go.Bar(x=df_flow['Date'], y=df_flow['외국인'], name='외국인', marker_color='#ef4444'))
            fig_net_buy.update_layout(barmode='group', xaxis_title='날짜', yaxis_title='순매수 (억원)', template="plotly_white")
            st.plotly_chart(fig_net_buy, use_container_width=True)

        with col2:
            st.subheader("세력 별 수급 원본 표")
            st.dataframe(df_flow, use_container_width=True, hide_index=True)
            
            # 간단 분석 로직
            last_foreign = df_flow.iloc[-1]['외국인']
            last_instit = df_flow.iloc[-1]['기관']
            
            st.markdown("#### 💡 Today's Flow Insight")
            if last_foreign > 0 and last_instit > 0:
                st.success(f"최근 영업일 기준 **외국인({last_foreign}억)과 기관({last_instit}억)이 양매수**를 기록하며 우호적인 시장 환경이 조성되었습니다.")
            elif last_foreign > 0:
                st.info(f"기관은 매도 우위이나, **외국인이 {last_foreign}억 원 순매수**하며 지수를 방어하고 있습니다.")
            elif last_instit > 0:
                st.info(f"외국인은 매도 우위이나, **기관이 {last_instit}억 원 순매수**하며 시장을 이끌고 있습니다.")
            else:
                st.warning("현재 기관과 외국인 모두 양매도를 기록 중입니다. 수급 보수적 접근이 필요합니다.")
    else:
        st.error("데이터를 수집하지 못했습니다. 네이버 금융 서버 또는 구조 변경을 확인하세요.")


# --- Tab 2: 계절성 트렌드 (Seasonality) ---
with tab2:
    st.header("섹터 대표주 10년 치 계절성 트렌드 (Real Data)")
    st.markdown("FinanceDataReader를 활용하여 주요 대표 종목의 최근 **10년간 월별 상승 확률(승률)**을 백테스팅한 실제 데이터입니다.")
    
    with st.spinner("최근 10년 치 주가 데이터를 분석 중입니다... (최초 1회 로딩 시 약 5~10초 소요)"):
        season_data = get_seasonality_data()
        
    if season_data:
        # 1. 데이터프레임화 (가로: 1~12월, 세로: 섹터명)
        df_hm = pd.DataFrame(season_data).T 
        df_hm.columns = [f"{i}월" for i in range(1, 13)]
        
        # 2. 히트맵 그리기
        st.markdown("#### 📊 월별/섹터별 평균 승률 히트맵")
        fig_hm = px.imshow(df_hm, 
                           labels=dict(x="월", y="대표 섹터", color="승률(%)"),
                           x=df_hm.columns, 
                           y=df_hm.index, 
                           color_continuous_scale="RdYlGn", # 직관적인 빨강-노랑-초록 색상
                           text_auto=True,
                           aspect="auto")
        st.plotly_chart(fig_hm, use_container_width=True)
        
        # 3. 현재 달 기준 분석 레이더 차트
        st.markdown("---")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            current_month = datetime.now().month
            st.write(f"#### 현재({current_month}월) 역사적 승률 Top")
            
            current_month_col = f"{current_month}월"
            if current_month_col in df_hm.columns:
                df_radar = df_hm[[current_month_col]].reset_index()
                df_radar.columns = ['Sector', 'Win Rate (%)']
                
                fig_radar = px.line_polar(df_radar, r='Win Rate (%)', theta='Sector', line_close=True,
                                          color_discrete_sequence=['#8b5cf6'])
                fig_radar.update_traces(fill='toself')
                st.plotly_chart(fig_radar, use_container_width=True)
            
        with col2:
            st.write("#### 💡 AI 계절성 인사이트")
            if current_month_col in df_hm.columns:
                best_sector = df_radar.loc[df_radar['Win Rate (%)'].idxmax()]
                st.success(f"과거 10년 데이터를 분석한 결과, **{current_month}월에는 '{best_sector['Sector']}'** 섹터가 상승할 확률이 **{best_sector['Win Rate (%)']}%**로 가장 높았습니다.")
            
            st.info("**이벤트 드리븐 (Event Driven) 주요 체크 포인트**")
            st.write("✔️ **2~3월**: 감사보고서 제출 및 배당락 이후 가치주 재평가 기간")
            st.write("✔️ **4월**: 1분기 실적 발표(어닝시즌)로 인한 실적주 차별화 장세")
            st.write("✔️ **11~12월**: 연말 배당 및 소비 시즌 (유통/배당주 강세)")
    else:
        st.error("계절성 데이터를 불러오는 데 실패했습니다.")


# --- Tab 3: 초개인화 (Personalization) ---
with tab3:
    st.header("당일 주도 테마 맞춤형 시나리오")
    st.markdown("네이버 금융의 실시간 테마 시세를 분석하여, 오늘 시장을 주도하는 테마와 편입 종목들을 안내합니다.")
    
    with st.spinner("네이버 금융 테마 리스트를 수집 중입니다..."):
        df_themes = get_theme_list()
        
    if not df_themes.empty:
        st.write("#### 🔥 오늘의 핫 테마 리스트 (Top 20)")
        
        # 관심 테마 선택
        theme_names = df_themes['테마명'].tolist()
        user_interest = st.selectbox(
            "💡 깊게 파보고 싶은 오늘의 관심 테마를 선택해주세요.",
            theme_names
        )
        
        st.markdown("---")
        
        selected_row = df_themes[df_themes['테마명'] == user_interest].iloc[0]
        st.success(f"🚀 **선택하신 '{user_interest}' 테마의 오늘 평균 등락률은 {selected_row['등락률(%)']}% 입니다.**")
        
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            st.markdown(f"#### '{user_interest}' 테마 핵심 편입 종목 현황")
            st.write("네이버 금융 기준 해당 테마에 편입된 주요 5개 종목의 실시간 시세입니다.")
            
            with st.spinner("종목 데이터를 수집 중입니다..."):
                df_stocks = get_theme_top_stocks(selected_row['링크'])
                
            if not df_stocks.empty:
                st.dataframe(df_stocks, use_container_width=True, hide_index=True)
                
                # --- 로또 픽 (Lotto Pick) 기능 ---
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown("### 🎲 오늘의 주도 테마 로또 픽 뽑기!")
                st.write("해당 테마 내에서 가장 모멘텀(등락률)이 강하거나 힘이 좋은 종목을 AI가 추첨해 드립니다!")
                
                if st.button("행운의 종목 뽑기 🍀", use_container_width=True):
                    # 등락률 숫자로 변환 후 가장 높은 1~2개 중 랜덤 픽
                    def parse_rate(val):
                        try:
                            return float(val.replace('%','').replace('+','').strip())
                        except:
                            return 0.0
                            
                    df_stocks['RateVal'] = df_stocks['등락률'].apply(parse_rate)
                    
                    # 상위 3개 중에서 하나를 랜덤으로 선택하여 로또 픽의 재미 요소 부여
                    top_candidates = df_stocks.sort_values(by='RateVal', ascending=False).head(3)
                    lucky_stock = top_candidates.sample(n=1).iloc[0]
                    
                    st.balloons() # 축포 터지기
                    st.success(f"🎉 **축하합니다! 오늘의 로또 픽 종목은 [{lucky_stock['종목명']}] (현재가: {lucky_stock['현재가']}, 등락률: {lucky_stock['등락률']}) 입니다!** 🚀")
                    st.info("단기 모멘텀이 매우 강하게 들어오고 있는 대장주급 종목입니다. (투자는 신중하게 결정하세요!)")
            else:
                st.warning("해당 테마의 종목 리스트를 불러올 수 없습니다.")
                
        with col_s2:
            st.markdown("#### 🤖 AI 투자 시나리오 판단")
            # 간단한 규칙 기반 투자 시나리오 제안
            if float(selected_row['등락률(%)']) > 3.0:
                st.write("📈 **매우 강한 자금 유입**")
                st.write("현재 시장 주도 테마로 선정되었습니다. 대장주를 중심으로 한 짧은 단기 트레이딩 접근이 유효할 수 있습니다.")
            elif float(selected_row['등락률(%)']) > 0:
                st.write("⚖️ **완만한 상승세**")
                st.write("조용히 우상향 중인 테마입니다. 향후 모멘텀(뉴스/정책) 발생 시 추가 슈팅의 가능성이 있습니다.")
            else:
                st.write("📉 **조정 중 (눌림목)**")
                st.write("현재 매수세가 약화되었습니다. 단기 급락 후 계절적 반등을 노리는 중기 관점의 분할 매수 모니터링이 필요합니다.")
                
    else:
        st.error("테마 리스트 수집에 실패했습니다.")

st.markdown("---")
st.caption("© 2026 Trend-Lotto Invest (Naver Finance Scraped Data) | *본 정보는 크롤링 기반 데이터로 오차가 있을 수 있으며 실제 투자 결과에 대한 책임은 지지 않습니다.*")
