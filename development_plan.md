# AlphaFinder 전면 분석 및 마스터 백업 문서 (Master Architectural Backup)

본 문서는 `trendstockanalist` 폴더 내의 전체 프로젝트 스캐닝 및 코드 분석을 바탕으로 작성된 **가장 완벽한 현재 상태의 아키텍처 및 백업 명세서**입니다.
이후 기능 추가 시 사이드 이펙트(Side Effect)를 방지하기 위해 파일별 역할과 의존성을 상세히 기술합니다.

---

## 📂 1. 디렉토리 구조 및 핵심 파일 (Directory Structure)

### 📌 루트 파일 (Root Files)
*   **`main.py`**: 프로젝트의 심장. FastAPI 앱 인스턴스화, CORS/보안 헤더 미들웨어(Security Headers), 라우터(`routers/`) 취합 기능. `APScheduler`를 이용해 AI 학습(Prophet), 테마(Theme) 및 수급 데이터 백그라운드 캐싱, 모의투자 수익률 갱신, 종목 지정가 도달 알림 발송 데몬을 구동합니다.
*   **`database.py`**: SQLAlchemy 연결 설정. 보안을 위해 소스 코드 내 하드코딩된 패스워드를 삭제하고 `os.getenv("DATABASE_URL")` 기반으로 연결되어 있습니다 (현재 Supabase 원격 PostgreSQL).
*   **`models.py`**: ORM 데이터베이스 테이블 명세. (`User`, `Portfolio`, `Comment`, `Vote`, `Alert`)
*   **`schemas.py`**: Pydantic 모델 명세. API 요청/응답 시 데이터 유효성 검사 및 타입 힌팅을 담당.
*   **`auth.py`**: JWT 기반 토큰 발급 및 비밀번호 해싱(bcrypt)을 담당하며, 토큰 위조 방지를 위한 `SECRET_KEY`를 환경 변수에서 로드합니다.
*   **`infra_module.py`**: 외부 인프라 통신. 한국투자증권(KIS) API 모듈 및 Telegram 봇 메시지 전송 모듈이 내장되어 있습니다.
*   **`ai_module.py`**: AI 처리 로직. Meta의 Prophet을 활용한 시계열 주가 예측 및 네이버 뉴스/섹터 기반 LLM(Google Gemini) 감성 분석 프롬프트 로직을 관장합니다.

### � 라우터 계층 (`routers/`) - 엔드포인트 분리
*   **`auth.py`**: `/api/register`, `/api/token` (회원가입 및 JWT 발급 로그인).
*   **`dashboard.py`**: `/api/market-data`(주요 지수), `/api/money-flow`(일별 외국인/기관 순매수 수급), `/api/themes`(인기 테마) 등 메인 홈 화면 데이터를 공급.
*   **`analysis.py`**: `/api/search` (종목 자동완성), `/api/stock_seasonality` (10년 치 주가 히트맵), `/api/stock_fundamentals` 등 종목별 상세 분석 및 AI 예측 데이터를 반환.
*   **`portfolio.py`**: 내 자산 관리 (`/api/portfolio`). 프론트에서 `sessionStorage` 토큰 기반으로 인증된 유저의 관심 종목/보유 주식을 등록·조회·삭제합니다.
*   **`community.py`**: 종목별 투자 의견(BULL/BEAR 투표) 및 댓글(Comments) 작성. 유저 랭킹보드용 수익률 조회를 담당.
*   **`alerts.py`**: 유저가 특정 종목의 "지정가 도달 알림(ABOVE/BELOW)"을 설정하는 CRUD 로직.
*   **`payment.py`**: 프리미엄 멤버십 권한 업그레이드 등 (현재 개발/테스트 보류 중).
*   **`system.py`**: 스파이더 봇 및 광고 연동을 위한 메타데이터. `sitemap.xml`, `robots.txt`, 구글 애드센스용 `ads.txt` 엔드포인트 제공.

### 📌 프론트엔드 (Templates & Static)
사용자의 페이지 이탈을 막기 위해 템플릿 엔진(Jinja2) 기반 SSR(서버 사이드 렌더링)과 SPA(싱글 페이지 애플리케이션)용 JS Fetch를 결합한 모던 인터페이스를 제공합니다.
*   **`base.html`**: 모든 HTML의 척추. Navbar, Footer, 전면 로딩 애니메이션(Coin Rain), 권한 통제(`sessionStorage` Auth 로직) 스크립트.
*   **`dashboard.html`**: 메인 페이지. 코스피/코스닥 주요 지수, 테마 순위, 기관/외국인 일자별 현황판.
*   **`review.html`**: 'AI 분석' 메인. 종목명 자동완성(Auto-Complete) 스크립트 내장. Plotly.js를 활용한 이동평균선/볼린저밴드/AI 예측 밴드 차트 및 매월 승률 10년 치 히트맵 표출.
*   **`portfolio.html`**: 회원 가입 및 로그인, 내가 담은 종목의 자산 비중 차트(Plotly Pie)와 지정가 알림 설정(Telegram), 모의수익률(Mock Return) 현황판. (최근 레이아웃 오류 수정됨).
*   **`themes.html`**: 산업별 테마주 정리 (Dashboard 테마 목록 클릭 시 상세 이동).
*   **`leaderboard.html`**: 전 유저의 모의투자 가상 수익률에 따른 순위 표출.
*   **기타**: `payment.html` (결제 준비), `policies.html` (이용약관 및 개인정보 보도).

---

## 🗄️ 2. 데이터베이스 스키마 백업 (DB Models)
Alembic을 통해 클라우드에 구성되어 있는 5개 핵심 테이블 구조입니다.

1.  **Users**: `id` (PK), `username` (Unique), `hashed_password`, `membership` (free/premium), `total_return` (가상 수익률), `created_at`.
2.  **Portfolio**: `id` (PK), `user_id` (FK-Users), `ticker` (종목코드), `target_price` (매수가), `qty` (수량), `added_at`.
3.  **Comments**: `id` (PK), `user_id` (FK-Users), `ticker` (종목), `content` (의견 내용).
4.  **Votes**: `id` (PK), `user_id` (FK), `ticker`, `vote_type` ('BULL' or 'BEAR'). 단일 종목 중복 투표 방지(클라이언트 측 캐싱).
5.  **Alerts**: `id` (PK), `user_id` (FK), `ticker`, `target_price`, `condition_type` ('ABOVE' 상향돌파 / 'BELOW' 하향이탈), `is_active` (1=활성/0=완료).

---

## 🛡️ 3. 보안 아키텍처 (Security Enhancements) - 최신 본
현재 시스템은 웹 애플리케이션의 핵심 취약점에 대응할 수 있도록 다음의 보안 장치를 완비했습니다.
1. **DB 및 환경 변수 보호**: 소스코드(`database.py`, `auth.py`)에 하드코딩된 패스워드와 JWT Secret Key를 제거하고, 오로지 인프라(Render) 상의 OS 환경 변수를 주입받도록 안전하게 격리함.
2. **CORS 제한 방어**: 악의적인 도메인에서 데이터를 탈취(Fetch)하지 못하게 `main.py`에 CORS 화이트리스트(허용된 5개 도메인 외 접속 차단) 적용 완료.
3. **Secure Headers 주입**: `main.py` 전역 통신 미들웨어를 통해 Helmet.js 수준의 방어 적용.
   - `X-Frame-Options: DENY` (Clickjacking / IFrame 위장 방어)
   - `X-Content-Type-Options: nosniff` (MIME 우회 공격 방어)
   - `Strict-Transport-Security` (HSTS 강제 암호화 수신)
4. **Auth State 탈취 방어**: 브라우저 탭을 꺼도 로그인이 영구적으로 유지되는 보안 허점을 막기 위해 프론트엔드(`base.html`, `portfolio.html`)의 인증 스토리지를 `localStorage`에서 `sessionStorage`로 전면 이관.

---

## ✅ 4. 최근 패치 및 해결된 버그 트래킹 (Resolved Issues)
- **[UI Bug]** 내 자산(`portfolio.html`) 데스크탑 화면에서 '입력폼' 껍데기(div) 내부에 '현황 보드판'이 잠겨 있어 왼쪽 세로 1열로 무너지는 현상 -> Grid Layout 독립 분리(수정 완료).
- **[Data Integrity]** 10년 치 주가 달력 승률 로직(히트맵) 호출 시 발생하는 `Numpy JSON Serialization` 오류(Numpy Float을 FastAPICache가 인식하지 못함) -> 파이썬 네이티브 `float()` 타입 캐스팅(수정 완료).
- **[Data Integrity]** 금요일 장 마감 후 또는 휴장일에 수급 데이터가 표시되지 않는 오류(단순 '현재일-N일' 차감 로직이 원인) -> `fdr.DataReader`로 최근 실제 영업일(Trading Days)만 추려오는 지능형 필터링(수정 완료).
- **[UX Enhancement]** 사용자가 종목명 입력 부분 고민 및 오타 방지 -> 네이버 금융 급 종목명 자동완성(Auto-Complete) API 구현 및 드롭다운 연동(추가 완료).

---

## 📝 5. 다음 단계 남은 기획안 (Pending Action Items)
*   **바이럴 마케팅 전략:** `html2canvas`로 렌더링된 현황표 하단에 AlphaFinder 로고를 워터마크로 박고, 이미지로 폰에 다운로드하는 기능.
*   **애드센스 연동:** 구글 광고 가입 및 페이지 내 삽입.
*   **현실 투자 연동:** KIS(한국투자증권) Oauth 연계 모의투자 대회를 "실전 투자 연계"로 치환.
