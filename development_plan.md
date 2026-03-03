# AlphaFinder 무결점 고도화 총괄 개발 계획서 및 백업 노트 (Zero-Defect Development Plan & Backup)

본 문서는 `skill.md`에 명시된 5단계 고도화 로드맵을 바탕으로 수립된 초기 기획안이자, **지금까지 실제 구현된 기능들의 업데이트 및 롤백용 백업 명세서**입니다.

---

## 🏗️ 1. 아키텍처 및 인프라 구현 (완료)
초기 아키텍처에서 계획된 목표들을 달성하였으며, 일부는 성능 향상을 위해 로직이 개선되었습니다.

*   **의존성(패키지) 관리:** `FastAPI`, `scikit-learn`, `prophet`, `google-generativeai`, `FinanceDataReader` 등 핵심 패키지 구성 및 버전 고정 완료.
*   **스케줄러 분리:** `APScheduler`를 통해 메인 스레드와 무관하게 백그라운드에서 AI 학습(Prophet), 데이터 캐싱(테마 및 수급), 모의투자 정산, 알림 발송 데몬이 독립적으로 구동되도록 구현 완료(`main.py`).
*   **외부 API 대비책(Circuit Breaker):** 증권사 API 연동 대기 중이나, 자체 크롤링 실패나 한국거래소 휴장일(주말/공휴일) 시에 데이터 크래시가 나지 않도록 `mock_data` 로직에 `FinanceDataReader` 검증기능 추가 완료.

---

## 🗄️ 2. 데이터베이스 및 서버 보안 구조 (완료 및 고도화)
**[오류 방지 핵심]** Alembic과 같은 툴 적용 전, SQLite를 임시로 사용하다가 현재 **프리 티어용 원격 Supabase PostgreSQL** 클라우드 DB로 이전 성공했습니다.

### 📝 데이터베이스 테이블 구조 및 보안 반영
1.  **DB 연결 보안:** 하드코딩된 패스워드를 삭제하고 `os.getenv("DATABASE_URL")` 기반으로 전환 완료하여 소스 코드 탈취 시에도 DB 방어 가능 (`database.py`).
2.  **`Users` 테이블:** `username`, `hashed_password`, `membership` (멤버십 등급), `total_return` (모의투자 수익률 캐싱용).
3.  **JWT 토큰 인증 보안:** 암호화 인증 키(`SECRET_KEY`)를 환경 변수화 하였으며, 영구적인 자동 로그인을 방지하기 위해 프론트엔드 캐시를 `localStorage`에서 `sessionStorage`로 전면 교체 (브라우저 종료 시 자동 로그아웃).
4.  **`Portfolio` 테이블:** 관심/투자 종목 추적.
5.  **`Alerts` 테이블:** 특정 가격 도달 시 서버 백그라운드 알림을 보내는 데 мон 활용.

---

## 🚀 3. Phase별 개발 완료 내역 및 추가 구현 현황

### Phase 1: AI (The Brain) - 예측 및 감성 분석 ✅
- **기술적 지표 및 Prophet:** `FastAPI` 라우터(`/analysis/{ticker}`) 내부에서 매일 밤 학습된 모델 데이터를 읽어와 Plotly 캔들스틱/밴드 차트 렌더링.
- **퀀트 점수(AI Score) 및 계절성(Seasonality):** 10년 치 주가 데이터의 달력 기반 수익성을 분석하는 हीट맵(Heatmap) 구현. 휴장일 제외 조건 및 `Numpy JSON Serialization` 에러 완벽 해결.

### Phase 2: Community & UI (The Heart) - 댓글 및 레이아웃 ✅
- **UI 레이아웃 교정:** 내 자산(Portfolio) 페이지가 왼쪽으로 쏠리는 레이아웃 붕괴 현상 수정 (Grid Layout 정상화). 데이터 보드 시인성 강화를 위해 '일자별 외국인/기관 순매수' 명칭으로 교체 및 설명 추가.
- **종목 검색 자동완성(Auto-Complete):** 사용자가 검색창에 '삼성'만 쳐도 관련 종목과 티커 코드가 드롭다운으로 조회되는 편의성 API(`/api/search`) 구현 및 JS 부착 완료.

### Phase 3: 인프라 (The Backbone) - API 및 보안(Security) ✅
- **서버사이드 시세 감시:** `FastAPI` 백그라운드 탭에서 가격 체크.
- **치명적 웹 공격 방어:** `main.py`에 CORS 화이트리스트 도입(지정된 도메인만 허용). 또한 Clickjacking, XSS를 막는 보안 HTTP 통신 헤더 주입 완료.

### Phase 4 & 5: 수익화 및 마케팅 (Monetization & Marketing) 🔄 (진행 중)
- **개발 계획 확정:** SEO를 위한 동적 메타 태그 최적화, `ads.txt` 삽입 등 애드센스 준비 로직 및 캡처 이미지를 활용한 '바이럴 전략' 등 마케팅 인프라 구성 준비 단계.

---

## 🛡️ 4. 배포(Deployment) 가이드라인

현재 Render.com을 통한 환경이며, GitHub `main` 릴리즈 푸시될 때 원격 서버로 CI/CD 배포되도록 구성되어 있습니다.

## 📝 다음 단계 액션 플랜
이 계획서를 바탕으로 당장 착수해야 할 작업은 다음과 같습니다.
1. 승인된 [수익화 파이프라인(광고 삽입 및 바이럴 공유 기능)] 개발 착수.
2. 커뮤니티 평판 시스템 및 유료 프리미엄 멤버십 권한 세분화 개발.
