# Trend-Lotto Invest: FastAPI 프론트엔드 리빌딩 백업 및 복구 매뉴얼

이 문서는 Streamlit에서 FastAPI로 전면 재구축(Rebuild)된 프로젝트의 핵심 로직과 구조를 요약한 **백업 및 복구 문서**입니다. 향후 서버 이전, 구조 변경, 또는 초기화 후 재구축이 필요할 때 이 문서를 참조하여 동일한 프로토타입을 신속하게 구성할 수 있습니다.

---

## 1. 리빌딩 배경 (Why FastAPI?)
- **이슈**: 기존 Streamlit은 리액트(React) 기반의 동적 렌더링 프레임워크로, `index.html`의 `<head>` 영역을 직접 제어할 수 없습니다. 이로 인해 **구글 애드센스 소유권 인증 스크립트**를 봇이 크롤링하지 못하는 문제("사이트를 검토할 수 없음")가 발생했습니다.
- **해결책**: 백엔드 로직(Python 데이터 분석 및 크롤링)은 그대로 유지하면서, 프론트엔드를 정적 HTML(Jinja2) 템플릿으로 분리하여 `<head>`에 애드센스 스크립트를 완벽하게 하드코딩하기 위해 **FastAPI 기반 웹 서비스**로 전환했습니다.

---

## 2. 필수 라이브러리 및 환경 구축 (`requirements.txt`)
프로젝트 재구축 시 우선적으로 아래 라이브러리들을 설치해야 합니다.

```bash
pip install fastapi uvicorn jinja2 pandas bs4 requests plotly finance-datareader
```

---

## 3. 프로젝트 디렉토리 구조
프로젝트는 크게 백엔드 API인 `main.py`와 프론트엔드 템플릿인 `templates/` 폴더로 나뉩니다.

```text
trendstockanalist/
├── main.py                    # FastAPI 웹 서버 및 백엔드 라우팅/크롤링 로직 핵심 파일
├── requirements.txt           # 파이썬 의존성 패키지 목록
├── 시나리오/                  # 백업/기획 문서 저장 폴더 (현재 위치)
└── templates/                 # 화면 UI 렌더링을 위한 Jinja2 HTML 파일들
    ├── base.html              # 모든 페이지의 뼈대 (Nav Bar, CSS, ★애드센스 스크립트 포함)
    ├── dashboard.html         # Tab 1: 자금 흐름 분석 (메인 페이지)
    ├── seasonality.html       # Tab 2: 섹터 계절성 트렌드(히트맵)
    ├── themes.html            # Tab 3: 테마 맞춤형 시나리오 (Top 20 테마 및 로또 픽)
    ├── review.html            # Tab 4: 기술적 매매 복기 및 퀀트 (차트 및 AI 스코어링)
    ├── portfolio.html         # Tab 5 & 6: 포트폴리오 관리 및 텔레그램 스텔스 알림 설정
    └── policies.html          # Tab 7: 필수 정책(애드센스 박탈 방지용 - 면책조항, 개인정보 등)
```

---

## 4. 백엔드 핵심 라우팅 및 로직 (`main.py`)

`main.py`는 FastAPI 서버를 띄우고 아래와 같은 라우트(경로)를 통해 HTML 템플릿에 데이터를 주입합니다.

1. **`@app.get("/")` - 자금 흐름 (Money Flow)**
   - **동작**: 네이버페이 증권 `iframe` 또는 BeautifulSoup 모의 데이터를 파싱합니다.
   - **전달 데이터**: 개인/기관/외국인 순매수 배열 (`flow_data`), AI 텍스트 피드백 (`insight`).
   - **UI 파일**: `dashboard.html`

2. **`@app.get("/seasonality")` - 계절성 트렌드**
   - **동작**: 과거 10년 치 섹터별 상승 승률(Mock-up/FDR 로직) 데이터를 2차원 배열(Z값)로 가공합니다.
   - **전달 데이터**: 히트맵용 X(월), Y(섹터), Z(승률값) 배열.
   - **UI 파일**: `seasonality.html`

3. **`@app.get("/themes")` - 테마 맞춤형 시나리오**
   - **동작**: `https://finance.naver.com/sise/theme.naver` 를 크롤링해 주도 테마 Top 20 및 편입 종목 5개의 시세를 파싱합니다.
   - **전달 데이터**: 테마 리스트(`themes`), 선택된 테마(`selected_theme_data`), 편입 종목(`stocks_data`).
   - **UI 파일**: `themes.html` (Javascript Canvas Confetti를 이용한 로또 애니메이션 기능 포함)

4. **`@app.get("/review")` - 매매 복기 및 퀀트 (Trading Review)**
   - **동작**: `FinanceDataReader`로 사용자가 검색한 종목코드의 6개월 캔들 데이터를 불러오고, Pandas의 `.rolling()`을 사용하여 이동평균선(MA), 볼린저밴드, RSI 등 기술적 지표를 내부 연산합니다. AI Score(0~100)를 산출합니다.
   - **전달 데이터**: JSON 직렬화된 OHLC 및 보조지표 차트 데이터(`chart_data`), 종합 국면 점수(`ai_score`).
   - **UI 파일**: `review.html` 

5. **`@app.get("/portfolio")` 및 `/policies` - 포트폴리오 및 정책**
   - **동작**: 별도의 백엔드 연산 없이 빈 템플릿을 반환합니다. 포트폴리오와 알림 봇 셋업은 DB 세팅의 복잡성을 줄이기 위해 브라우저의 전역 저장소(`localStorage`)를 조작하는 Javascript로 완벽히 대체되었습니다. (서버리스 구현)

---

## 5. 프론트엔드 핵심 구조 및 복구 시 주의사항

- **CSS 프레임워크**: `Tailwind CSS (CDN)` 사용. 별도의 `style.css` 파일 없이 `base.html`의 `<head>` 부분에 `<script src="https://cdn.tailwindcss.com"></script>` 구문으로 불러옵니다.
- **차트 라이브러리**: Streamlit의 st.plotly_chart 대신, 프론트엔드에서 `Plotly.js (CDN)`를 로드해 Javascript로 차트를 그립니다 (`Plotly.newPlot()`).
- **★ 애드센스 삽입부 (`base.html`) 복구**:
  만약 호스팅 업체가 바뀌거나 애드센스 코드가 날아갔을 때는 `templates/base.html` 파일의 `<head>` 태그 내에 아래 형태의 코드를 항상 첫 번째로 확보해야 합니다.
  ```html
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-본인고유코드입력" crossorigin="anonymous"></script>
  ```
- **Javascript JSON Parsing 버그 방지**:
  Jinja2 변수(`{{ variable }}`)를 Javascript 변수로 받을 때는 줄바꿈 문자로 인한 Syntax Error를 방지하기 위해 템플릿 리터럴(Backtick `)과 `JSON.parse`를 무조건 감싸서 사용해야 합니다.
  ```javascript
  const rawData = `{{ data_json | safe }}`;
  const parsedData = JSON.parse(rawData);
  ```

---

## 6. 어플리케이션 실행 방법 (실섭 구동)

프로젝트 폴더 내 최상단 위치에서 아래 명령어를 실행하여 서버를 가동합니다.
```bash
python -m uvicorn main:app --reload
```
또는
```bash
python main.py
```
이후 Chrome 등 브라우저 창에 `http://127.0.0.1:8000` 을 입력하여 접속합니다.
