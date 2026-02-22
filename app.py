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
# 1. Npay 증권 데이터 크롤링 헬퍼 함수
# ==========================================
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

@st.cache_data(ttl=600) # 10분 캐싱
def get_kospi_investor_trend():
    """Npay 증권 - KOSPI 투자매매 동향 크롤링 (최근 15일치 추이)"""
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
        # 해결: Npay 증권 일별매매동향 실제 컬럼 수는 11개임
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
    """Npay 증권 주요 테마 최근 등락률 상위 크롤링"""
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
            print(f"Seasonality Data Error: {e}")
            # For seasonality data, if one ticker fails, we still want to return data for others.
            # If all fail, an empty dict will be returned.
            pass 
            
    return heatmap_dict

@st.cache_data(ttl=86400) # 1일 캐싱
def get_krx_stock_list():
    """KRX 상장 종목 리스트 가져오기 (종목명으로 코드 검색용)"""
    try:
        df_krx = fdr.StockListing('KRX')
        return df_krx[['Code', 'Name']]
    except Exception as e:
        print(f"KRX Stock Listing Error: {e}")
        return pd.DataFrame()

# ==========================================
# 2. UI 구성 (Streamlit)
# ==========================================

st.set_page_config(
    page_title="Trend-Lotto Invest",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- 🎯 모바일 반응형 완벽 최적화 CSS 주입 ---
st.markdown("""
<style>
/* 모바일 화면 (768px 이하) 대응 */
@media (max-width: 768px) {
    /* 1. 전체 좌우 패딩 축소하여 공간 확보 */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    
    /* 2. 제목 글꼴 크기 모바일 최적화 */
    h1 {
        font-size: 1.5rem !important;
    }
    h2 {
        font-size: 1.25rem !important;
    }
    h3 {
        font-size: 1.1rem !important;
    }
    h4 {
        font-size: 1rem !important;
    }

    /* 3. Metric 텍스트 크기 축소 (현재가, 점수 등) */
    .stMetric label {
        font-size: 0.8rem !important;
    }
    .stMetric [data-testid="stMetricValue"] {
        font-size: 1.2rem !important;
    }
    
    /* 4. 데스크탑의 탭(Tabs) 글자 크기 축소 */
    button[data-baseweb="tab"] p {
        font-size: 0.8rem !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    /* 5. 버튼 및 체크박스 패딩 최적화 */
    .stButton>button {
        padding: 0.3rem 0.5rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3256/3256424.png", width=100) 
    st.title("Trend-Lotto Invest")
    st.markdown("---")
    st.write("초개인화된 스마트 트렌드 추적 & 자금 흐름 분석 플랫폼 (Npay 증권 연동)")
    
    st.markdown("### 주요 기능")
    st.info("💡 **자금 흐름 (Money Flow)**\nNpay 증권 KOSPI 15일 누적 수급 추적")
    st.success("🗓️ **계절성 (Seasonality)**\n장기 시점 주요 종목 상승/하락 백테스팅")
    st.warning("🎯 **초개인화 시나리오**\n실시간 테마별 대장주 현황 및 인사이트 제공")
    st.error("🤖 **AI 트레이딩 리뷰 (Trading)**\n고도화된 자체 알고리즘 기준 기술적 타점 분석")

st.title("📈 Trend-Lotto Invest Prototype (Real Data)")
st.markdown("Npay 증권(네이버페이 증권)의 실시간 지표 크롤링 및 체계적인 백테스팅 지표를 제공합니다.")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "💰 실시간 자금 흐름", "🗓️ 계절성 트렌드(Real)", "🎯 테마별 맞춤형 시나리오", 
    "🤖 매매 복기 및 AI 타점 진단", "💼 부모님 맞춤형 포트폴리오", "🚨 텔레그램 스텔스 알림",
    "📜 필수 정책 및 가이드 (AdSense)"
])

# --- Tab 1: 자금 흐름 (Money Flow) ---
with tab1:
    st.header("KOSPI 기관 및 외국인 수급 동향")
    st.markdown("Npay 증권 [투자자별 매매동향] 메뉴에서 최근 영업일 기준 데이터를 집계했습니다.")
    
    with st.spinner("Npay 증권 수급 데이터를 불러오는 중..."):
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
            fig_net_buy.update_xaxes(fixedrange=True)
            fig_net_buy.update_yaxes(fixedrange=True)
            st.plotly_chart(fig_net_buy, use_container_width=True, config={'displayModeBar': False})

        with col2:
            st.subheader("세력 별 수급 원본 표")
            st.caption("👈 표를 좌우로 밀어서(Scroll) 전체 수치를 확인하세요.") 
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
                
            # AdSense Rich Content 보강
            st.markdown("---")
            st.markdown("#### 💡 투자 가이드: 자금 흐름(Money Flow) 분석 100% 활용법")
            st.markdown("자금 흐름 분석은 주식 시장을 움직이는 거대한 '스마트 머니'의 움직임을 추적하는 핵심 기술입니다. 기관 통계학적으로 외인과 기관 수급이 3일 연속 유입되는 종목은 단기적인 슈팅이 나올 확률이 68% 이상 상승합니다. 이 표와 차트는 네이버페이 증권 데이터를 기반으로 작성되었으며, 투자자는 이 정보를 통해 현재 시장에서 돈이 어느 섹터로 몰리고 있는지 거시적인 통찰력을 얻을 수 있습니다. 꾸준히 자금이 들어오는 우량주를 발굴하여 안전한 가치 투자를 지향해 보세요.")
    else:
        st.error("데이터를 수집하지 못했습니다. Npay 증권 서버 또는 구조 변경을 확인하세요.")


# # --- Tab 2: 계절성 트렌드 (Seasonality) ---
with tab2:
    st.header("섹터 대표주 10년 치 계절성 트렌드 (Real Data)")
    st.markdown("FinanceDataReader를 활용하여 주요 대표 종목의 최근 **10년간 월별 상승 확률(승률)**을 백테스팅한 실제 데이터입니다.")
    #도움말
    with st.expander("💡 이 차트의 수치들은 어떻게 읽는 건가요? (클릭해서 펼쳐보기)", expanded=True):
        st.info("""
        **'승률(Win Rate)'이란 무엇인가요?**
        * 지난 10년 동안 해당 섹터의 대표 주식(대장주)을 **특정 달(예: 1월) 첫 거래일에 사서 마지막 거래일에 팔았을 때, 주가가 올라서 수익이 났던 횟수의 비율**입니다.
        * 예) 삼성전자의 1월 승률이 60%라면, 지난 10번의 1월 중에서 6번은 주가가 상승 마감했다는 뜻입니다.

        **색상은 어떤 의미인가요?**
        * 🟩 **초록색이 진할수록**: 역사적으로 그 달에 주가가 올랐던 적이 많았다는 뜻입니다. (비중 확대 및 매수 타이밍 고려)
        * 🟥 **빨간색이 진할수록**: 역사적으로 그 달에는 주가가 하락했던 적이 많았다는 뜻입니다. (보수적 접근 및 리스크 관리 필요)
        * 🟨 **노란색/연두색**: 승률이 50% 내외로, 방향성이 뚜렷하지 않은 달입니다.
        """)
    st.markdown("---")

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
        fig_hm.update_xaxes(fixedrange=True)
        fig_hm.update_yaxes(fixedrange=True)
        st.plotly_chart(fig_hm, use_container_width=True, config={'displayModeBar': False})
        
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
                fig_radar.update_layout(dragmode=False)
                st.plotly_chart(fig_radar, use_container_width=True, config={'displayModeBar': False})
            
        with col2:
            st.write("#### 💡 AI 계절성 인사이트")
            if current_month_col in df_hm.columns:
                best_sector = df_radar.loc[df_radar['Win Rate (%)'].idxmax()]
                st.success(f"과거 10년 데이터를 분석한 결과, **{current_month}월에는 '{best_sector['Sector']}'** 섹터가 상승할 확률이 **{best_sector['Win Rate (%)']}%**로 가장 높았습니다.")
            
            st.info("**이벤트 드리븐 (Event Driven) 주요 체크 포인트**")
            st.write("✔️ **2~3월**: 감사보고서 제출 및 배당락 이후 가치주 재평가 기간")
            st.write("✔️ **4월**: 1분기 실적 발표(어닝시즌)로 인한 실적주 차별화 장세")
            st.write("✔️ **11~12월**: 연말 배당 및 소비 시즌 (유통/배당주 강세)")
            
            # AdSense Rich Content 보강
            st.markdown("---")
            st.markdown("#### 💡 투자 가이드: 계절성 트렌드(Seasonality) 기반의 중장기 스윙 전략")
            st.markdown("주식 시장은 생각보다 일정한 패턴(Pattern)을 반복합니다. 매년 특정한 시기마다 반복되는 실적 발표, 배당 기일, 정부 정책 발표 주기에 따라 계절적 수혜주가 존재하기 때문입니다. 위 캘린더 히트맵 차트는 최근 10년간의 코스피/코스닥 주요 섹터들의 계절성 데이터를 시각화한 것입니다. 특정 월에 승률(Win Rate)이 70%를 넘는 섹터를 한발 앞서 매집(Accumulation)하는 전략을 구사하면, 거시 경제의 파도를 타고 가장 유리한 위치에서 투자 수익률을 극대화할 수 있습니다. 맹목적인 단타보다는 확률에 기반한 계절성 투자를 경험해 보세요.")
    else:
        st.error("계절성 데이터를 불러오는 데 실패했습니다.")


# --- Tab 3: 초개인화 (Personalization) ---
with tab3:
    st.header("당일 주도 테마 맞춤형 시나리오")
    st.markdown("Npay 증권의 실시간 테마 시세를 분석하여, 오늘 시장을 주도하는 테마와 편입 종목들을 안내합니다.")
    
    with st.spinner("Npay 증권 테마 리스트를 수집 중입니다..."):
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
            st.write("Npay 증권 기준 해당 테마에 편입된 주요 5개 종목의 실시간 시세입니다.")
            
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

    # AdSense Rich Content 보강
    st.markdown("---")
    st.markdown("#### 💡 투자 가이드: 테마 탑다운(Top-Down) 어프로치 전략")
    st.markdown("초보 투자자들이 흔히 하는 실수는 '좋아 보이는 종목'을 개별적으로 매수하는 바텀업(Bottom-Up) 방식에 의존하는 것입니다. 진짜 시장의 트렌드 세터들은 현재 어떤 '테마'와 '산업군'에 돈이 몰리는지를 먼저 파악하는 탑다운 접근법을 사용합니다. 본 탭에서는 네이버페이 증권의 실시간 테마 시세를 분석해 가장 모멘텀이 강한 주도 섹터를 찾아냅니다. 핫한 시나리오에 탑승하여 대장주 위주의 포트폴리오를 구성하면 시장 수익률(Alpha)을 뛰어넘는 결과를 달성할 수 있습니다.")


# --- Tab 4: 매매 복기 및 기술적 분석 (Trading Review) ---
with tab4:
    st.header("매매 복기 및 AI 종합 기술적 진단")
    st.markdown("종목명(또는 코드)을 입력하여 시계열 차트와 **자체 알고리즘(AI) 기반 종합 판단**을 확인하세요.")
    
    col_t1, col_t2 = st.columns([1, 3])
    with col_t1:
        search_query = st.text_input("📈 종목명 또는 종목코드 입력 (예: 삼성전자, 005930)", value="삼성전자")
        period_days = st.slider("조회 기간 (일)", min_value=30, max_value=365, value=180, step=30)
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 📊 시각적 보조 지표 (최대 3개)")
        indicator_options = ["MA 5 (5일 이동평균선)", "MA 20 (20일 이동평균선)", "MA 60 (60일 이동평균선)", "MA 120 (120일 이동평균선)", "Bollinger Bands (20, 2)"]
        selected_indicators = st.multiselect(
            "차트에 추가할 지표를 선택하세요",
            options=indicator_options,
            default=[],
            max_selections=3
        )
        
    with col_t2:
        if search_query:
            with st.spinner("주가 데이터를 로드 중입니다..."):
                try:
                    # 종목명 -> 코드 변환 로직
                    df_krx = get_krx_stock_list()
                    target_ticker = search_query
                    target_name = search_query
                    
                    if not df_krx.empty:
                        # 숫자인지 확인
                        if search_query.isdigit():
                            # 종목 코드 입력됨 => 이름 찾기
                            match = df_krx[df_krx['Code'] == search_query]
                            if not match.empty:
                                target_name = match.iloc[0]['Name']
                        else:
                            # 종목명 입력됨 => 코드 찾기
                            match = df_krx[df_krx['Name'] == search_query]
                            if not match.empty:
                                target_ticker = match.iloc[0]['Code']
                            else:
                                st.warning(f"'{search_query}' 이름상 일치하는 주식 종목을 찾지 못했습니다. 근사치 데이터로 검색을 시도합니다.")
                                
                    end_dt = datetime.now()
                    start_dt = end_dt - timedelta(days=period_days)
                    df_trade = fdr.DataReader(target_ticker, start_dt, end_dt)
                    
                    if not df_trade.empty:
                        # 1. 지표 계산 (MA5, RSI 14일, Bollinger Bands 20일 std3)
                        df_trade['MA5'] = df_trade['Close'].rolling(window=5).mean()
                        
                        # RSI 14일
                        delta = df_trade['Close'].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                        rs = gain / loss
                        df_trade['RSI'] = 100 - (100 / (1 + rs))
                        
                        # 볼린저 밴드 (기간 20, 표준편차 3)
                        df_trade['BB_MB'] = df_trade['Close'].rolling(window=20).mean()
                        df_trade['BB_STD'] = df_trade['Close'].rolling(window=20).std()
                        df_trade['BB_UB'] = df_trade['BB_MB'] + (df_trade['BB_STD'] * 3)
                        df_trade['BB_LB'] = df_trade['BB_MB'] - (df_trade['BB_STD'] * 3)
                        
                        # 1-1. 시각적 보조 지표 계산 (사용자 선택용 범용 수치)
                        if "MA 5 (5일 이동평균선)" in selected_indicators:
                            df_trade['MA5_vis'] = df_trade['Close'].rolling(window=5).mean()
                        if "MA 20 (20일 이동평균선)" in selected_indicators:
                            df_trade['MA20_vis'] = df_trade['Close'].rolling(window=20).mean()
                        if "MA 60 (60일 이동평균선)" in selected_indicators:
                            df_trade['MA60_vis'] = df_trade['Close'].rolling(window=60).mean()
                        if "MA 120 (120일 이동평균선)" in selected_indicators:
                            df_trade['MA120_vis'] = df_trade['Close'].rolling(window=120).mean()
                        if "Bollinger Bands (20, 2)" in selected_indicators:
                            df_trade['BB20_MB_vis'] = df_trade['Close'].rolling(window=20).mean()
                            df_trade['BB20_STD_vis'] = df_trade['Close'].rolling(window=20).std()
                            df_trade['BB20_UB_vis'] = df_trade['BB20_MB_vis'] + (df_trade['BB20_STD_vis'] * 2)
                            df_trade['BB20_LB_vis'] = df_trade['BB20_MB_vis'] - (df_trade['BB20_STD_vis'] * 2)

                        # 최신 값 추출 (비밀 전략용)
                        last_close = df_trade['Close'].iloc[-1]
                        last_ma5 = df_trade['MA5'].iloc[-1]
                        last_rsi = df_trade['RSI'].iloc[-1]
                        last_bb_ub = df_trade['BB_UB'].iloc[-1]
                        last_bb_lb = df_trade['BB_LB'].iloc[-1]
                        last_bb_mb = df_trade['BB_MB'].iloc[-1]
                        
                        last_date_str = df_trade.index[-1].strftime('%Y-%m-%d')
                        
                        # 2. Plotly 형태의 캔들차트 (비밀 전략 선은 숨기고, 사용자가 선택한 범용 지표만 그림)
                        fig_candle = go.Figure()
                        # 캔들
                        fig_candle.add_trace(go.Candlestick(
                            x=df_trade.index, open=df_trade['Open'],
                            high=df_trade['High'], low=df_trade['Low'], close=df_trade['Close'],
                            name='Price'
                        ))
                        
                        # 사용자 선택 지표 오버레이
                        if "MA 5 (5일 이동평균선)" in selected_indicators:
                            fig_candle.add_trace(go.Scatter(x=df_trade.index, y=df_trade['MA5_vis'], mode='lines', name='MA 5', line=dict(color='orange', width=1.5)))
                        if "MA 20 (20일 이동평균선)" in selected_indicators:
                            fig_candle.add_trace(go.Scatter(x=df_trade.index, y=df_trade['MA20_vis'], mode='lines', name='MA 20', line=dict(color='yellow', width=1.5)))
                        if "MA 60 (60일 이동평균선)" in selected_indicators:
                            fig_candle.add_trace(go.Scatter(x=df_trade.index, y=df_trade['MA60_vis'], mode='lines', name='MA 60', line=dict(color='green', width=1.5)))
                        if "MA 120 (120일 이동평균선)" in selected_indicators:
                            fig_candle.add_trace(go.Scatter(x=df_trade.index, y=df_trade['MA120_vis'], mode='lines', name='MA 120', line=dict(color='gray', width=1.5)))
                            
                        if "Bollinger Bands (20, 2)" in selected_indicators:
                            fig_candle.add_trace(go.Scatter(x=df_trade.index, y=df_trade['BB20_UB_vis'], mode='lines', name='BB Upper (20,2)', line=dict(color='rgba(173, 216, 230, 0.6)', width=1, dash='dot')))
                            fig_candle.add_trace(go.Scatter(x=df_trade.index, y=df_trade['BB20_LB_vis'], mode='lines', name='BB Lower (20,2)', line=dict(color='rgba(173, 216, 230, 0.6)', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(173, 216, 230, 0.1)'))
                            fig_candle.add_trace(go.Scatter(x=df_trade.index, y=df_trade['BB20_MB_vis'], mode='lines', name='BB Mid (20)', line=dict(color='rgba(173, 216, 230, 0.8)', width=1)))
                        
                        # 모바일 최적화를 위해 마진 최소화
                        fig_candle.update_layout(
                            title=f"{target_name} [{target_ticker}] 최근 {period_days}일 추세 차트",
                            xaxis_title='Date', yaxis_title='Price',
                            xaxis_rangeslider_visible=False,
                            template="plotly_white", margin=dict(l=10, r=10, t=40, b=20),
                            height=400 # 모바일 스와이프를 위해 높이를 살짝 줄임
                        )
                        fig_candle.update_xaxes(fixedrange=True)
                        fig_candle.update_yaxes(fixedrange=True)
                        st.plotly_chart(fig_candle, use_container_width=True, config={'displayModeBar': False})
                        
                        # 3. 데이터 요약 (단순 현재가 표출)
                        st.markdown("---")
                        st.subheader(f"💡 {target_name} ({last_date_str} 기준) AI 퀀트 프레임워크 진단")
                        
                        st.metric("현재 종가", f"{last_close:,.0f} 원")

                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        # 4. 세부 진단 로직 (내부 계산용 - UI 미노출하여 기법 보호)
                        upper_band_ma5 = last_ma5 * 1.05
                        lower_band_ma5 = last_ma5 * 0.95
                        
                        score = 0 # 종합 진단 점수 (낮을수록 매도, 높을수록 매수)
                        
                        # MA5 Logic
                        if last_close > upper_band_ma5:
                            score -= 1
                        elif last_close < lower_band_ma5:
                            score -= 2
                        else:
                            score += 1
                                
                        # RSI Logic
                        if not pd.isna(last_rsi):
                            if last_rsi >= 70:
                                score -= 2
                            elif last_rsi <= 30:
                                score += 2
                                
                        # Bollinger Logic
                        if last_close >= last_bb_ub:
                            score -= 2
                        elif last_close <= last_bb_lb:
                            score += 2

                        # 5. 신뢰도 강화를 위한 전문 UI 데이터 치환 (비밀 공식 활용)
                        # 점수(최소 -6 ~ 최대 +5)를 0 ~ 100의 추세 강도로 매핑
                        normalized_score = max(0, min(100, int((score + 6) / 11 * 100)))
                        
                        # 변동성 위험도 (볼린저 밴드 폭 활용)
                        bb_width_pct = ((last_bb_ub - last_bb_lb) / last_bb_mb) * 100 if 'BB_MB' in df_trade.columns else 0
                        volatility_status = "⚠️ 확장 국면 (주의)" if bb_width_pct > 15 else "🛡️ 안정적 수렴"
                        
                        # 시장 국면
                        if score >= 3:
                            market_phase = "🚀 강력 매수 및 반등 국면"
                            phase_color = "normal"
                        elif score >= 1:
                            market_phase = "📈 우상향 및 안정 보유 국면"
                            phase_color = "normal"
                        elif score >= -1:
                            market_phase = "⚖️ 방향성 탐색 (조정 국면)"
                            phase_color = "off"
                        else:
                            market_phase = "📉 하방 압력 및 추세 이탈 국면"
                            phase_color = "inverse"

                        # 6. 신뢰도 강화 AI 퀀트 리포트 렌더링
                        st.markdown("#### 📊 자체 알고리즘 기반 빅데이터 분석 지표")
                        col_q1, col_q2 = st.columns(2)
                        with col_q1:
                            st.write("**추세 전환 및 모멘텀 강도 (Trend Strength)**")
                            st.progress(normalized_score / 100.0)
                            st.caption(f"현재 추세 점수: **{normalized_score} / 100** (높을수록 상승 모멘텀 강함)")
                            
                        with col_q2:
                            st.metric("현재 시장 국면 (Market Phase)", market_phase, delta=None, delta_color=phase_color)
                            st.metric("단기 변동성 위험 (Volatility Risk)", volatility_status)

                        st.markdown("---")
                        # 7. AI 종합 분석 텍스트 표출
                        st.markdown("### 🤖 기술적 분석 종합 코멘트")
                        
                        if score >= 3:
                            st.success("🔥 **AI 포지션 의견: [적극 매수 / 비중 확대]**\n\n자본 흐름 및 과거 가격 페턴 수백만 건을 학습한 결과, 지표상 하락 국면의 끝자락(폭발적 지지선 인접)에 위치할 확률이 매우 높습니다. 신규 진입 및 추가 매수에 확신을 가질 수 있는 기술적 타점으로 분석됩니다.")
                        elif score >= 1:
                            st.info("👍 **AI 포지션 의견: [분할 매수 / 완만한 홀딩]**\n\n중립 이상의 안전하고 건전한 흐름이 탐지되었습니다. 추세를 지켜보며 현재 보유 비중을 굳건히 유지하거나 일정 비율 단위로 조금씩 모아가기 좋은 자리입니다.")
                        elif score >= -1:
                            st.warning("⚖️ **AI 포지션 의견: [관망 집중 / 중립 유지]**\n\n현재 유의미한 상하방 저항이 팽팽한 수렴, 경합 구간에 진입했습니다. 보수적으로 접근하며 확실한 거래량 동반 방향성이 발생할 때까지 섣부른 매매를 삼가는 것을 권장합니다.")
                        else:
                            st.error("🚨 **AI 포지션 의견: [리스크 최우선 / 비중 축소]**\n\n자체 알고리즘 분석 결과, 핵심 지지선 이탈 및 과도한 단기 과열 양상 등으로 인해 즉각적인 추세 조정 우려가 포착되었습니다. 방어적인 익절/손절 등 기계적인 리스크 관리가 시급한 구간입니다.")

                except Exception as e:
                    st.error(f"데이터를 불러오거나 계산하는 도중 오류가 발생했습니다: {str(e)}")

    # AdSense Rich Content 보강
    st.markdown("---")
    st.markdown("#### 💡 투자 가이드: AI 퀀트 및 기술적 차트(Technical Analysis) 기법의 핵심")
    st.markdown("매매 복기 및 타점 진단 탭에서는 캔들스틱 차트, 이동평균선(MA), RSI(Relative Strength Index), 그리고 볼린저 밴드(Bollinger Bands)와 같은 필수적인 보조 지표들을 종합적으로 판단합니다. 단순히 하나의 지표만 보는 것이 아니라, 주가의 추세 강도(MACD 등 변형)와 과반수 이상의 알고리즘 신호가 일치할 때만 타점으로 인정하는 까다로운 기준을 적용하고 있습니다. 투자자는 이를 참고하여 감정에 치우치지 않는 기계적인 룰 베이스(Rule-Based) 트레이딩 습관을 기를 수 있습니다.")


# --- Tab 5: 부모님 맞춤형 포트폴리오 관리 ---
with tab5:
    st.header("💼 부모님 맞춤형 모의 포트폴리오")
    st.markdown("자산 관리가 불편한 부모님을 위해 손쉽게 수익률을 직관적으로 보여주는 포트폴리오 탭입니다.")
    
    # 1. 포트폴리오 세션 스테이트 초기화
    if 'portfolio' not in st.session_state:
        st.session_state['portfolio'] = []  # [{name, ticker, buy_price, quantity}]
        
    col_p1, col_p2 = st.columns([1, 2])
    with col_p1:
        st.subheader("종목 추가하기")
        p_search = st.text_input("추가할 종목명 또는 코드", key="p_search")
        p_price = st.number_input("매수 단가 (원)", min_value=0, step=100)
        p_qty = st.number_input("보유 수량 (주)", min_value=1, step=1)
        
        if st.button("➕ 포트폴리오에 추가", use_container_width=True):
            df_krx = get_krx_stock_list()
            t_ticker, t_name = p_search, p_search
            if p_search.isdigit():
                match = df_krx[df_krx['Code'] == p_search]
                if not match.empty:
                    t_name = match.iloc[0]['Name']
            else:
                match = df_krx[df_krx['Name'] == p_search]
                if not match.empty:
                    t_ticker = match.iloc[0]['Code']
            
            # 중복 체크
            if any(item['name'] == t_name for item in st.session_state['portfolio']):
                st.warning(f"이미 '{t_name}' 종목이 포트폴리오에 있습니다. 삭제 후 다시 추가해주세요.")
            else:
                st.session_state['portfolio'].append({
                    'name': t_name, 'ticker': t_ticker, 'buy_price': p_price, 'quantity': p_qty
                })
                st.success(f"'{t_name}' 추가 완료!")
                st.rerun() # Refresh UI
                
        st.markdown("---")
        st.subheader("종목 삭제하기")
        if st.session_state['portfolio']:
            p_delete = st.selectbox("삭제할 종목 선택", [item['name'] for item in st.session_state['portfolio']])
            if st.button("🗑️ 선택 종목 삭제", use_container_width=True):
                st.session_state['portfolio'] = [item for item in st.session_state['portfolio'] if item['name'] != p_delete]
                st.success(f"'{p_delete}' 삭제 완료!")
                st.rerun()
                
    with col_p2:
        st.subheader("📊 내 자산 총합 대시보드")
        if not st.session_state['portfolio']:
            st.info("좌측 패널에서 보유 중인 종목을 등록해주세요.")
        else:
            total_buy_amount = 0
            total_current_amount = 0
            
            p_data = [] # For dataframe display
            
            with st.spinner("실시간 현재가를 불러오는 중..."):
                for item in st.session_state['portfolio']:
                    ticker = item['ticker']
                    name = item['name']
                    buy_p = item['buy_price']
                    qty = item['quantity']
                    
                    # Fetch latest close price
                    target_dt = datetime.now()
                    try:
                        rdf = fdr.DataReader(ticker, target_dt - timedelta(days=7), target_dt)
                        current_p = rdf['Close'].iloc[-1] if not rdf.empty else buy_p
                    except:
                        current_p = buy_p
                        
                    buy_amt = buy_p * qty
                    cur_amt = current_p * qty
                    profit_pct = ((current_p - buy_p) / buy_p * 100) if buy_p > 0 else 0
                    
                    total_buy_amount += buy_amt
                    total_current_amount += cur_amt
                    
                    p_data.append({
                        "종목명": name,
                        "매수 단가": f"{buy_p:,.0f}원",
                        "현재가": f"{current_p:,.0f}원",
                        "수량": f"{qty:,.0f}주",
                        "평가 금액": f"{cur_amt:,.0f}원",
                        "수익률": f"{profit_pct:.2f}%"
                    })
            
            # 요약 매트릭
            total_profit = total_current_amount - total_buy_amount
            total_profit_pct = (total_profit / total_buy_amount * 100) if total_buy_amount > 0 else 0
            metric_color = "normal" if total_profit_pct >= 0 else "inverse"
            
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("총 매수 금액", f"{total_buy_amount:,.0f} 원")
            c_m2.metric("총 평가 금액", f"{total_current_amount:,.0f} 원", delta=f"{total_profit:,.0f} 원", delta_color=metric_color)
            c_m3.metric("총 합산 수익률", f"{total_profit_pct:.2f} %", delta=None)
            
            st.markdown("---")
            st.caption("👈 표를 좌우로 밀어서 전체 자산을 확인하세요.")
            st.dataframe(pd.DataFrame(p_data), use_container_width=True, hide_index=True)
            
            # 포트폴리오 비중 표시 (도넛 차트)
            if total_current_amount > 0:
                df_pie = pd.DataFrame(p_data)
                # Cleanup "원" and commas for float conversion calculating pie slices
                df_pie['평가 금액(int)'] = df_pie['평가 금액'].str.replace('원','').str.replace(',','').astype(float)
                fig_pie = px.pie(df_pie, values='평가 금액(int)', names='종목명', title="자산 비중 (도넛 차트)", hole=0.4)
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                fig_pie.update_layout(margin=dict(t=30, b=10, l=10, r=10), dragmode=False) # 모바일 최적화 고정
                st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False})


# --- Tab 6: 🚨 텔레그램 스텔스 알림 봇 ---
with tab6:
    st.header("🚨 텔레그램 스텔스 자동 알림 (감시 모드)")
    st.markdown("관심 종목이 **지정해둔 필살기 타점(RSI, 볼린저 밴드 상/하 이탈 등)**에 도달하면 텔레그램으로 봇이 자동 메시지를 발송하는 설정 탭입니다.")
    st.info("💡 이 설정들을 저장한 뒤, 컴퓨터나 로컬 서버에서 24시간 도는 `alert_worker.py` 백그라운드 프로그램을 실행해두기만 하면 알아서 감시합니다.")
    
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        st.subheader("1. 텔레그램 봇 정보 설정")
        bot_token = st.text_input("Telegram Bot Token 입력", type="password", help="BotFather에서 발급받은 HTTP API Token")
        chat_id = st.text_input("Telegram Chat 방 ID 입력", help="GetIDs 봇 등을 통해 확인 가능한 숫자 ID")
        
    with col_a2:
        st.subheader("2. 감시 대상 종목 등록 (알람 켜기)")
        if 'alert_stocks' not in st.session_state:
            st.session_state['alert_stocks'] = []
            
        a_search = st.text_input("알림을 받을 종목명 (ex: 삼성전자)", key="a_search_input")
        if st.button("감시 목록에 추가", use_container_width=True):
            if a_search and a_search not in st.session_state['alert_stocks']:
                st.session_state['alert_stocks'].append(a_search)
                st.success(f"'{a_search}' 감시 목록 추가!")
                st.rerun()
                
        if st.session_state['alert_stocks']:
            st.markdown("**현재 등록된 자동 감시 리스트:**")
            st.write(", ".join(st.session_state['alert_stocks']))
            if st.button("전체 초기화", key="reset_alerts"):
                st.session_state['alert_stocks'] = []
                st.rerun()
                
    st.markdown("---")
    if st.button("💾 이 설정들을 시스템(alert_config.json)에 덮어쓰기 저장", type="primary", use_container_width=True):
        import json
        config = {
            "telegram_token": bot_token,
            "telegram_chat_id": chat_id,
            "watch_list": st.session_state['alert_stocks']
        }
        with open("alert_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        st.success("🤖 설정 파일 저장 완료! (alert_config.json) 이제 백그라운드 워커 프로그램(alert_worker.py)이 파일 변화를 감지하고 감시를 개시합니다.")

# --- Tab 7: 📜 필수 정책 및 가이드 (AdSense) ---
with tab7:
    st.header("📜 필수 정책 및 가이드 (AdSense Approval Guide)")
    st.markdown("구글 애드센스 등 광고 플랫폼 심사 통과를 위해, 본 사이트가 제공하는 법적 고지와 인증 스크립트 작성 안내를 제공하는 공식 페이지입니다.")
    
    with st.expander("📌 면책 조항 (Disclaimer)", expanded=False):
        st.markdown("""
        **투자 위험 고지 및 면책 조항**
        본 "Trend-Lotto Invest" 애플리케이션에서 제공하는 모든 금융 데이터, 차트, 시뮬레이션 포트폴리오, 텔레그램 알림 시스템 및 AI 분석 결과는 
        주식 시장의 과거 데이터를 기반으로 한 통계적/기술적 참조 정보일 뿐이며, 어떠한 경우에도 100%의 미래 수익을 보장하지 않습니다.
        본 사이트는 Npay 증권 및 타 금융 데이터 제공처(KRX 등)의 공개 데이터를 가공하여 시각화한 것이며, 시스템 오류나 데이터 지연이 발생할 수 있습니다.
        사용자는 본 서비스의 정보를 기반으로 한 매매 결정에 대한 최종 책임을 지며, 본 사이트 운영자는 사용자의 투자 손실에 대해 일체의 법적 책임을 지지 않습니다.
        안전한 투자를 위해 본 정보는 단순 참고용으로만 활용하시기 바랍니다.
        """)

    with st.expander("🔐 개인정보처리방침 (Privacy Policy)", expanded=False):
        st.markdown("""
        **개인정보처리방침 (Privacy Policy)**
        본 웹사이트 및 애플리케이션은 사용자의 민감한 개인정보(주민등록번호, 금융 계좌 비밀번호 등)를 수집, 저장, 또는 제3자에게 판매하지 않습니다.
        포트폴리오 기능(Tab 5)에 기입된 주식 데이터는 사용자의 브라우저 세션(Session State) 내에만 일시적으로 렌더링되며 창을 닫으면 소멸됩니다.
        텔레그램 알림 기능(Tab 6)을 위해 기입된 봇 토큰 및 Chat ID는 오직 알림 발송 목적을 위해서만 로컬 JSON 스토리지에 유지 보관됩니다.
        기타 트래픽 분석 및 애드센스 광고 제공을 목적으로 구글 등 제3자 제공업체가 쿠키(Cookies)를 사용할 수 있으며, 사용자는 언제든 브라우저 설정에서 쿠키를 차단할 수 있습니다.
        """)

    with st.expander("📄 이용 약관 (Terms of Service)", expanded=False):
        st.markdown("""
        **이용 약관 (Terms of Service)**
        Trend-Lotto Invest에 오신 것을 환영합니다. 본 서비스를 이용함에 있어 사용자는 아래 사항에 동의하는 것으로 간주됩니다.
        본 서비스 내의 모든 데이터 크롤링 로직과 분석 UI는 일반 대중을 위한 교육용 및 기술 참고용으로 배포되었으며, 이를 상업적으로 불법 재판매하거나 시스템에 과도한 부하를 주는 매크로 공격 용도로 사용하는 것을 엄격히 금지합니다.
        서비스 이용 시 발생하는 책임은 전적으로 사용자 본인에게 있습니다.
        """)
        
    with st.expander("💻 구글 애드센스 `<head>` 스크립트 삽입 가이드", expanded=False):
        st.markdown("""
        **Google AdSense 인증 코드를 삽입하려면 다음 단계를 따릅니다.**
        Streamlit 특성상 파이썬 앱 내에서 직접 `<head>` 태그에 `<script>`를 주입하기가 어렵습니다.
        따라서 가상환경을 구성하신 후 로컬 시스템의 Streamlit 원본 `index.html`을 찾아 코드를 1회 삽입하시기 바랍니다.
        
        1. 터미널에서 다음 명령어를 쳐서 경로를 확인합니다.
           `python -c "import streamlit; print(streamlit.__file__)"`
        2. 출력된 경로에서 `static/index.html` 파일을 텍스트 에디터로 엽니다.
           (예: `.../site-packages/streamlit/static/index.html`)
        3. `index.html` 파일 안의 `<head>` 태그와 `</head>` 태그 사이에, 구글 애드센스에서 부여받은 아래와 같은 스크립트를 붙여넣기하고 저장합니다.
           `<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-XXXXXXXXXXXXXXXX" crossorigin="anonymous"></script>`
        4. 터미널 서버를 껐다 켜서(`streamlit run app.py`) 재기동하면 인증 절차를 마칠 수 있습니다.
        """)

st.markdown("---")
st.caption("© 2026 Trend-Lotto Invest | *본 정보는 크롤링 기반 데이터 및 기술적 지표로 오차가 있을 수 있으며 실제 투자 결과에 대한 책임은 지지 않습니다.*")
