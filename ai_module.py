import os
import json
import pandas as pd
from datetime import datetime
import FinanceDataReader as fdr
from google import genai
from google.genai import types
from prophet import Prophet

# Gemini API 설정 (환경변수에서 읽어옴, 없으면 None)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

def train_prophet_model(ticker: str, df: pd.DataFrame):
    """
    Prophet 모델을 학습시키고 향후 30일 가격 예측 밴드를 반환합니다.
    """
    try:
        if len(df) < 60: # 데이터가 너무 적으면 예측 불가
            return None
            
        # Prophet 요구 형식('ds', 'y')으로 변환
        prep_df = df.reset_index()[['Date', 'Close']].rename(columns={'Date': 'ds', 'Close': 'y'})
        
        # 모델 학습 (주말 제외 설정 등 기본 셋업)
        m = Prophet(daily_seasonality=False)
        m.fit(prep_df)
        
        # 미래 30일 데이터프레임 생성 (주말을 포함하지만 대략적인 밴드 제공용)
        future = m.make_future_dataframe(periods=30)
        forecast = m.predict(future)
        
        # 최근 30일에 해당하는 예측 결과만 추출
        forecast_30d = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(30)
        
        # 반환용 포맷 변환
        result = []
        for index, row in forecast_30d.iterrows():
            result.append({
                "date": row['ds'].strftime("%Y-%m-%d"),
                "predicted": round(row['yhat'], 2),
                "lower": round(row['yhat_lower'], 2),
                "upper": round(row['yhat_upper'], 2)
            })
        return result
    except Exception as e:
        print(f"Prophet training error for {ticker}: {e}")
        return None

def analyze_news_sentiment_with_llm(ticker: str, news_list: list):
    """
    LLM(Gemini)을 활용하여 뉴스 헤드라인 배열에 대한 감성 분석 및 코멘트를 생성합니다.
    API 키가 없거나 실패할 경우 None을 반환합니다.
    """
    if not GEMINI_API_KEY or not client:
        return None
        
    try:
        news_text = "\n".join([f"- {news}" for news in news_list[:10]]) # 최대 10개만 분석
        
        prompt = f"""
        당신은 금융 시장을 분석하는 AI 퀀트 애널리스트입니다.
        다음은 '{ticker}' 종목에 대한 최근 주요 뉴스 헤드라인입니다.

        {news_text}
        
        위 뉴스들을 종합적으로 판단하여 다음 JSON 형식으로 정확히 답변해 주세요. (마크다운 포맷이나 다른 텍스트는 빼고 순수 JSON만 반환할 것)
        {{
            "sentiment": "positive/neutral/negative 중 하나",
            "score": 0~100 사이의 긍정 점수 (100이 가장 긍정적),
            "summary_comment": "뉴스를 종합한 한 줄 요약 코멘트 (예: '수주 소식으로 인한 강한 상승 모멘텀이 기대됩니다.')"
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        text = response.text.strip()
        
        # 마크다운 블록이 섞여있을 수 있어 파싱 처리
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
            
        parsed = json.loads(text)
        return parsed
    except Exception as e:
        print(f"LLM Sentiment Error for {ticker}: {e}")
        return None
