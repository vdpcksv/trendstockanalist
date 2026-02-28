# AlphaFinder 무결점 고도화 총괄 개발 계획서 (Zero-Defect Development Plan)

`skill.md`에 명시된 5단계 고도화 로드맵을 바탕으로, **기존 서비스의 안정성을 해치지 않으면서(Zero-Downtime)** 신규 기능을 안전하게 확장하기 위한 상세 개발, DB 설계 및 예외 처리 계획입니다.

---

## 🏗️ 1. 아키텍처 및 인프라 보강 계획
새로운 기능들이 기존 웹 서버 리소스를 갉아먹거나 병목(Bottleneck)을 일으키지 않도록 분리된 아키텍처를 지향합니다.

*   **의존성(패키지) 관리:** 모델 관리에 필요한 패키지(`scikit-learn`, `prophet`), LLM API 클라이언트(`google-generativeai`, `openai`), 통신(`httpx`, `python-telegram-bot`)을 `requirements.txt`에 버전 고정하여 추가.
*   **비동기 워커 분리:** AI 학습(`Phase 1`)과 모의투자 수익률 정산(`Phase 2`), 알림 발송(`Phase 3`)은 메인 웹 프로세스가 아닌 독립적인 스케줄러(예: Celery + Redis, 또는 분리된 APScheduler 데몬)에서 실행하여 사용자가 웹페이지를 탐색할 때 느려지지 않도록 합니다.
*   **외부 API 대비책(Circuit Breaker):** 증권사 API나 LLM API 장애 시 웹앱 전체가 멈추는 것을 방지하기 위해 타임아웃과 캐시 폴백(Cache Fallback) 메커니즘을 둡니다.

---

## 🗄️ 2. 데이터베이스 안전 마이그레이션 전략 (DB Schema)
**[오류 방지 핵심]** 기존 테이블을 코드에서 직접 `DROP` 하거나 강제 `ALTER` 하지 않습니다. **Alembic**과 같은 마이그레이션 툴을 사용하여 버전 관리를 하고 장애 시 즉각 롤백(Rollback)할 수 있는 체계를 잡습니다.

### 📝 데이터베이스 추가/변경 명세
1.  **`Users` 테이블 변경 (Phase 2, 4)**
    *   `ADD total_return FLOAT DEFAULT 0.0;` (모의투자 수익률 캐싱용 - 실시간 계산을 피하기 위함)
    *   `ADD membership VARCHAR(20) DEFAULT 'free';` (멤버십 등급)
2.  **`Comments` 테이블 신설 (Phase 2)**
    *   `id` (PK), `user_id` (FK), `ticker` (종목코드), `content` (VARCHAR), `created_at` (DATETIME)
    *   종목별 조회가 많으므로 `ticker` 컬럼에 인덱스(Index) 생성.
3.  **`Votes` 테이블 신설 (Phase 2)**
    *   `id` (PK), `user_id` (FK), `ticker`, `vote_type` ('BULL' or 'BEAR'), `created_at`
    *   한 유저가 한 종목에 하루 한 번만 투표하도록 Unique 제약조건 고려.
4.  **`Alerts` 테이블 신설 (Phase 3)**
    *   `id` (PK), `user_id` (FK), `ticker`, `target_price`, `condition_type` ('ABOVE', 'BELOW'), `is_active` (BOOLEAN)

---

## 🚀 3. Phase별 개발 절차 및 안전망(QA) 계획

### Phase 1: AI (The Brain) - 예측 및 감성 분석
*   **개발 단계:**
    1. 주가 데이터셋 추출 및 Prophet/LSTM 모델 학습 자동화 배치 스크립트 작성.
    2. LLM 네이버 뉴스 감성 분석 프롬프트 최적화 및 연동.
*   **오류 방지 및 QA:**
    *   **LLM Rate Limit 방어:** API 호출 횟수 초과로 에러 반환 시 프론트에 "현재 AI 분석 요청이 많아 대기 중입니다."와 같은 Graceful(우아한) 에러 메시지 표출. 결과를 Redis 등에 24시간 캐싱하여 API 비용과 호출 빈도 최소화.
    *   **모델 결과 캐싱:** 주가 예측 추론 결과는 사용자 요청 시마다 돌리지 않고, 매일 밤 생성된 정적 결괏값(JSON 등)을 읽어오는 형태로 속도를 확보.

### Phase 2: Community (The Heart) - 댓글 및 랭킹
*   **개발 단계:**
    1. XSS(크로스 사이트 스크립팅) 및 SQL Injection 필터링이 적용된 댓글 작성/조회 API 구현.
    2. 자정에 실행될 전 유저 모의투자 수익률 정산 배치 로직 로컬 테스트.
*   **오류 방지 및 QA:**
    *   정산 시 DB Deadlock 방지를 위해 유저 데이터를 500명씩 Chunk 단위로 쪼개어 트랜잭션을 처리(`Commit`).
    *   에러 발생 시 슬랙이나 텔레그램으로 즉각 개발자에게 알림이 오도록 에러 핸들링 부착.

### Phase 3: 인프라 (The Backbone) - API 및 알림
*   **개발 단계:**
    1. KIS 개발자 센터 API 연동 클래스 작성 및 실시간 호가/시세 조회 연동.
    2. 서버 사이드 시세 감시 및 Telegram 알림 발송 데몬 제작.
*   **오류 방지 및 QA:**
    *   **Fallback 구조:** KIS API가 주말 점검 등으로 통신 불능 상태가 될 경우를 대비해, 예외(`Exception`) 캐치 시 기존 네이버 금융 크롤링 모듈이 작동하는 비상 루틴 1단계 마련.
    *   알림 중복 발생 억제 로직 추가 (한 번 가격에 도달하여 알림이 간 후에는 며칠간 휴지기 설정 등).

### Phase 4 & 5: 수익화 및 홍보 (Monetization & Marketing)
*   **개발 단계:** 페이먼트 모듈(토스 페이먼츠/포트원 등) 연동, SEO 적용(Sitemap, MetaOG 생성기).
*   **오류 방지 및 QA:**
    *   결제 모듈은 무조건 테스트 환경(Sandbox)에서 "통장 잔고 부족", "결제 중 브라우저 종료", "네트워크 에러" 시나리오를 100% 재현하여 트랜잭션 정상 롤백 확인.

---

## 🛡️ 4. 배포(Deployment) 가이드라인

상태를 예측할 수 없는 에러를 방지하기 위해 **반드시 3단계 배포 프로세스**를 도입합니다.

1.  **Dev (로컬 개발 환경):** IDE 내부에서 모든 기능 및 예외상황 점검.
2.  **Staging (테스트 서버):** 실제 DB의 최근 백업본을 복사해둔 환경. 여기서 Alembic 마이그레이션이 정상 작동하는지, 크롤링 IP가 차단되지 않는지 테스트합니다.
3.  **Production (운영 서버):** 심야 코어 타임 이외의 시간(예: 새벽 3시)에 배포. 배포 직전 반드시 기존 DB 풀 백업 수행.

## 📝 다음 단계 액션 플랜
이 계획서를 바탕으로 당장 착수해야 할 작업은 다음과 같습니다.
1.  프로젝트 내 `requirements.txt` 점검 및 마이그레이션 툴(`alembic`) 도입.
2.  **Phase 3의 인프라(KIS API 연동 등)**을 먼저 적용하여 크롤링으로 인한 에러 불안정성을 원천적으로 제거한 뒤, AI 및 커뮤니티 기능을 얹는 상향식 개발 순서를 권장합니다.
