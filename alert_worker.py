import os
import json
import time
import requests
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta

CONFIG_FILE = "alert_config.json"
CHECK_INTERVAL_SECONDS = 3600  # 1시간마다 검사

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"설정 파일 읽기 오류: {e}")
        return None

def send_telegram_message(token, chat_id, text):
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 텔레그램 발송 성공: {text[:20]}...")
    except Exception as e:
        print(f"텔레그램 발송 실패: {e}")

def get_krx_stock_list():
    try:
        df_krx = fdr.StockListing('KRX')
        return df_krx[['Code', 'Name']]
    except Exception as e:
        print(f"KRX Stock Listing Error: {e}")
        return pd.DataFrame()

def check_indicators_and_alert():
    config = load_config()
    if not config:
        print("설정 파일(alert_config.json)이 없거나 잘못되었습니다. 감시를 건너뜁니다.")
        return

    token = config.get("telegram_token", "")
    chat_id = config.get("telegram_chat_id", "")
    watch_list = config.get("watch_list", [])

    if not token or not chat_id or not watch_list:
        print("텔레그램 토큰, Chat ID, 또는 감시 종목 리스트가 비어있습니다.")
        return

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 감시 시작: {watch_list}")
    df_krx = get_krx_stock_list()

    for stock_query in watch_list:
        target_ticker = stock_query
        target_name = stock_query
        
        # 종목명 -> 코드 변환
        if not df_krx.empty:
            if stock_query.isdigit():
                match = df_krx[df_krx['Code'] == stock_query]
                if not match.empty:
                    target_name = match.iloc[0]['Name']
            else:
                match = df_krx[df_krx['Name'] == stock_query]
                if not match.empty:
                    target_ticker = match.iloc[0]['Code']
                else:
                    print(f"'{stock_query}' 이름상 일치하는 주식 종목을 찾지 못했습니다. 건너뜁니다.")
                    continue

        try:
            # 넉넉하게 60일치 데이터 가져오기 (이평선, RSI, 볼린저 밴드 계산용)
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=60)
            df = fdr.DataReader(target_ticker, start_dt, end_dt)

            if df.empty or len(df) < 20:
                continue

            # 지표 계산
            close_prices = df['Close']
            
            # 1. RSI 14일 계산
            delta = close_prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

            # 2. 볼린저 밴드 (기간 20, 표준편차 3) 계산
            df['BB_MB'] = close_prices.rolling(window=20).mean()
            df['BB_STD'] = close_prices.rolling(window=20).std()
            df['BB_UB'] = df['BB_MB'] + (df['BB_STD'] * 3)
            df['BB_LB'] = df['BB_MB'] - (df['BB_STD'] * 3)

            # 최신 값 추출
            last_close = close_prices.iloc[-1]
            last_rsi = df['RSI'].iloc[-1]
            last_bb_ub = df['BB_UB'].iloc[-1]
            last_bb_lb = df['BB_LB'].iloc[-1]

            alerts = []

            # 조건 1: RSI 30 이하 (과매도)
            if not pd.isna(last_rsi) and last_rsi <= 30:
                alerts.append(f"📉 **RSI 과매도 도달 ({last_rsi:.1f} <= 30)**\n👉 초강력 매수 타점이 임박했습니다!")

            # 조건 2: RSI 80 이상 (과매수)
            if not pd.isna(last_rsi) and last_rsi >= 80:
                alerts.append(f"📈 **RSI 과매수 도달 ({last_rsi:.1f} >= 80)**\n👉 차익 실현 및 관망 타점이 임박했습니다!")

            # 조건 3: 볼린저밴드 상단 이탈 (초강력 익절)
            if not pd.isna(last_bb_ub) and last_close >= last_bb_ub:
                alerts.append(f"🔥 **볼린저 밴드(20,3) 상단 돌파!**\n현재가: {last_close:,.0f}원 (상단선: {last_bb_ub:,.0f}원)\n👉 초과열 상태입니다. 익절을 고려하세요.")

            # 조건 4: 볼린저밴드 하단 이탈 (초강력 매수)
            if not pd.isna(last_bb_lb) and last_close <= last_bb_lb:
                alerts.append(f"🥶 **볼린저 밴드(20,3) 하단 이탈!**\n현재가: {last_close:,.0f}원 (하단선: {last_bb_lb:,.0f}원)\n👉 과도한 투매 상태입니다. 초강력 매수/물타기를 고려하세요.")

            if alerts:
                msg = f"🚨 **[Trend-Lotto Alert] {target_name} ({target_ticker})** 🚨\n\n"
                msg += "\n\n".join(alerts)
                send_telegram_message(token, chat_id, msg)

        except Exception as e:
            print(f"[{target_name}] 지표 계산 또는 발송 중 오류: {e}")

        # 종목 간 호출 딜레이 방지
        time.sleep(1)

if __name__ == "__main__":
    print("🤖 Trend-Lotto 텔레그램 감시 봇을 시작합니다...")
    while True:
        check_indicators_and_alert()
        print(f"다음 검사는 {CHECK_INTERVAL_SECONDS}초 뒤에 실행됩니다.")
        time.sleep(CHECK_INTERVAL_SECONDS)
