import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(
    page_title="Trend-Lotto Invest",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 사이드바 설정 (프로토타입 소개)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3256/3256424.png", width=100) # 주식/성장 아이콘 임시
    st.title("Trend-Lotto Invest")
    st.markdown("---")
    st.write("초개인화된 스마트 트렌드 추적 & 자금 흐름 분석 플랫폼")
    
    st.markdown("### 주요 기능")
    st.info("💡 **자금 흐름 (Money Flow)**\n거래량 및 기관/외인 수급 데이터 추적")
    st.success("🗓️ **계절성 (Seasonality)**\n핵심 섹터별 시기적 상승 패턴 분석")
    st.warning("🎯 **초개인화 시나리오**\n관심사 기반 맞춤형 투자 인사이트 제공")

# 메인 헤더
st.title("📈 Trend-Lotto Invest Prototype")
st.markdown("시장의 핵심 트렌드와 자금 흐름을 한눈에 파악하세요.")

# 기능 탭 구성
tab1, tab2, tab3 = st.tabs(["💰 자금 흐름 분석", "🗓️ 계절성 트렌드", "🎯 초개인화 시나리오"])

# --- 데이터 생성 (Mock Data) ---
@st.cache_data
def load_money_flow_data():
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=30)
    data = {
        'Date': dates,
        '기관 순매수(억)': np.random.randint(-500, 1500, size=30),
        '외국인 순매수(억)': np.random.randint(-1000, 2000, size=30),
        '거래대금(억)': np.random.randint(5000, 20000, size=30)
    }
    return pd.DataFrame(data)

@st.cache_data
def load_sector_seasonality():
    sectors = ['반도체', '바이오', '2차전지', '소프트웨어', '로봇', '금융']
    win_rates = [68, 55, 62, 71, 48, 59]
    return pd.DataFrame({'Sector': sectors, 'Win Rate (%)': win_rates})

# --- Tab 1: 자금 흐름 (Money Flow) ---
with tab1:
    st.header("기관 및 외국인 실시간 수급 동향")
    st.markdown("최근 30일간의 주요 수급 주체의 자금 유입을 추적합니다.")
    
    df_flow = load_money_flow_data()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("순매수 추이 (최근 30일)")
        fig_net_buy = go.Figure()
        fig_net_buy.add_trace(go.Bar(x=df_flow['Date'], y=df_flow['기관 순매수(억)'], name='기관', marker_color='#3b82f6'))
        fig_net_buy.add_trace(go.Bar(x=df_flow['Date'], y=df_flow['외국인 순매수(억)'], name='외국인', marker_color='#ef4444'))
        fig_net_buy.update_layout(barmode='group', xaxis_title='날짜', yaxis_title='순매수 (억원)', template="plotly_white")
        st.plotly_chart(fig_net_buy, use_container_width=True)

    with col2:
        st.subheader("시장 전체 거래대금 추이")
        fig_volume = px.line(df_flow, x='Date', y='거래대금(억)', markers=True, 
                             line_shape='spline', color_discrete_sequence=['#10b981'])
        fig_volume.update_layout(xaxis_title='날짜', yaxis_title='거래대금 (억원)', template="plotly_white")
        st.plotly_chart(fig_volume, use_container_width=True)
        
    st.markdown("#### 🔥 수급 폭발 종목 (Mock List)")
    st.dataframe(pd.DataFrame({
        "종목명": ["에코프로", "삼성전자", "한미반도체", "SK하이닉스", "루닛"],
        "연속 순매수일정": ["5일", "3일", "4일", "2일", "7일"],
        "수급 주체": ["외국인", "기관", "양매수", "외국인", "양매수"],
        "전일대비등락률": ["+4.2%", "+1.5%", "+8.7%", "+2.1%", "+12.4%"]
    }), use_container_width=True)


# --- Tab 2: 계절성 트렌드 (Seasonality) ---
with tab2:
    st.header("섹터별 시기상승 패턴 (Seasonality)")
    st.markdown("과거 5년치 데이터를 분석하여 특정 월이나 분기에 상승 확률이 높은 섹터를 리포팅합니다.")
    
    col1, col2 = st.columns([1, 2])
    
    df_season = load_sector_seasonality()
    
    with col1:
        st.write("#### 1분기 역사적 승률 Top")
        fig_radar = px.line_polar(df_season, r='Win Rate (%)', theta='Sector', line_close=True,
                                  color_discrete_sequence=['#8b5cf6'])
        fig_radar.update_traces(fill='toself')
        st.plotly_chart(fig_radar, use_container_width=True)
        
    with col2:
        st.write("#### 주요 이벤트 캘린더 (Event Driven)")
        st.info("**2월**: MWC (모바일 월드 콩그레스) 개최 ➔ 통신장비, AI소프트웨어 섹터 수급 유입 기대")
        st.success("**3월**: 감사보고서 제출 시즌 ➔ 재무 건전성 상위 기업 및 고배당 기업 선호 현상")
        st.warning("**4월**: 1분기 실적 발표 (어닝시즌) ➔ 반도체 수출 지표 견조함에 따른 상승 기대")
        
        st.write("")
        st.markdown("###### 예상 상승 확률 매트릭스")
        # 간단한 히트맵 데이터 (Mock)
        heatmap_data = np.random.randint(40, 90, size=(5, 12))
        months = [f"{i}월" for i in range(1, 13)]
        sectors_hm = ['반도체', '제약바이오', '자동차', '엔터', '게임']
        fig_hm = px.imshow(heatmap_data, labels=dict(x="월", y="섹터", color="승률(%)"),
                           x=months, y=sectors_hm, color_continuous_scale="Viridis", text_auto=True)
        st.plotly_chart(fig_hm, use_container_width=True)


# --- Tab 3: 초개인화 (Personalization) ---
with tab3:
    st.header("관심사 맞춤형 AI 투자 시나리오")
    st.markdown("사용자의 평소 관심사와 최근 핫한 시장의 테마를 교차 결합하여 인사이트를 제공합니다.")
    
    user_interest = st.selectbox(
        "💡 귀하의 주요 관심 분야를 선택해주세요.",
        ("우주/항공", "인공지능(AI)", "전기차/배터리", "의료/디지털헬스", "K-컨텐츠/엔터")
    )
    
    st.markdown("---")
    
    if user_interest == "인공지능(AI)":
        st.success(f"🤖 **선택하신 '{user_interest}' 기반의 투자 시나리오가 준비되었습니다.**")
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            st.markdown("#### Scenario: 온디바이스 AI 시대의 개막")
            st.write("""
            스마트폰, PC 등 기기 자체에서 AI를 구동하는 '온디바이스 AI' 생태계가 본격화되고 있습니다. 
            AI 모델의 가벼워짐과 동시에 기기 내장형 NPU(신경망처리장치) 수요가 폭발할 전망입니다.
            현재 자금 흐름상 '소프트웨어 AI'에서 다시금 '하드웨어 및 칩셋'으로 매수세가 순환하고 있습니다.
            """)
            st.markdown("**관심 섹터**: NPU 설계 팹리스, 고대역폭메모리(HBM) 관련 장비사, AI 솔루션 최적화 기업")
        with col_s2:
            st.metric(label="테마 연관 자금유입 (최근 1주일)", value="3,200 억", delta="12%", delta_color="normal")
            st.metric(label="대표 종목 평균 상승률", value="14.5%", delta="4.2%", delta_color="normal")
            
    elif user_interest == "전기차/배터리":
         st.success(f"🔋 **선택하신 '{user_interest}' 기반의 투자 시나리오가 준비되었습니다.**")
         st.markdown("#### Scenario: 차세대 전고체 배터리와 리사이클링")
         st.write("안전성과 주행거리를 혁신할 전고체 배터리 상용화 일정이 구체화되고 있습니다. 동시에 폐배터리 리사이클링 법안 통과로 관련 생태계의 밸류에이션 재평가가 이루어지고 있는 시점입니다.")
         
    else:
        st.info(f"선택하신 '{user_interest}'에 대한 맞춤형 분석 리포트를 AI가 생성 중입니다. (기본 프로토타입 UI 대기 화면)")
        st.progress(60)

# 푸터 마무리는 페이지 하단에.
st.markdown("---")
st.caption("© 2026 Trend-Lotto Invest. All rights reserved. | *본 정보는 투자 참고용이며 실제 투자 결과에 대한 책임은 지지 않습니다.*")
