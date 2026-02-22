Trend-Lotto Invest 핵심 개발 가이드

1\. 기술 스택 (Tech Stack) - antigravity 대체

Web Framework: \* Streamlit: 초기 프로토타입 및 데이터 시각화 웹을 빠르게 만들 때.



FastAPI + React/Vue: 상업화를 위한 빠르고 안정적인 API 서버와 프론트엔드 분리 구축 시.



Data Analysis \& AI: pandas, scikit-learn, 자연어 처리(NLP) 모델 (뉴스/트렌드 분석용).



Database: PostgreSQL (사용자 포트폴리오, 시계열 주식 데이터 등 대용량 데이터 저장).



2\. 핵심 기능 구현 논리 (Core Logic)

자금 흐름 (Money Flow) 분석: 거래량 급증, 기관/외국인 수급 연속성, 섹터별 자금 이동 데이터를 추적하는 알고리즘 구축.



계절성 (Seasonality) 패턴화: 과거 5~10년 치의 시계열 데이터를 분석해, 특정 시기(예: 연말 배당철, 특정 산업의 성수기)에 상승 확률이 높은 종목 발굴.



초개인화 (Personalization) 시나리오: 사용자의 평소 관심사(예: 과학, 기계, 신기술 등)와 시장의 주요 트렌드를 교차 분석하여, 사용자가 흥미를 느끼면서도 승률이 높은 투자 시나리오 제공.



3\. 주식/금융 데이터 수집 (Data Sources)

한국투자증권 Open API 또는 키움증권 Open API (실시간 수급 및 차트 데이터).



Dart (전자공시시스템) API 연동: 기업의 재무제표, 성장성 등 펀더멘털 분석 자동화.



FinanceDataReader, yfinance (글로벌/국내 과거 주가 데이터 백테스팅용).



4\. 상업화 체크리스트 (Commercialization)

법적 검토: 단순 정보 제공을 넘어설 경우, 유사투자자문업 신고 등 금융 관련 법적 규제 필히 확인.



보안: 사용자 개인정보, 관심사, 금융 데이터에 대한 철저한 암호화 (SSL/TLS 적용).



수익 모델(BM): 기본 기능은 무료로 제공하되, 고급 자금 흐름 리포트나 맞춤형 포트폴리오 알림은 구독형(Premium)으로 구성.

