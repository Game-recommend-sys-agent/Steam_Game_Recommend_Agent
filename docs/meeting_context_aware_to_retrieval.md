## 5) 오늘 회의에서 합의가 필요한 내용(1차 기획안)

회의 효율을 위해 “질문 목록”이 아니라, **일단 이렇게 가자**는 1차 기획안을 먼저 제시합니다.  
회의에서는 아래 안을 기준으로 **수정/보완/확정**만 하면 됩니다.

### 5.1 1~8 병합: context_bundle v0.1(권장안)

| 항목 | 권장안 |
|---|---|
| **SSOT 원칙** | 필드명/타입/nullable/단위는 문서/코드에서 단일 진실 유지 |
| **games 구조** | `map[appid(str)] -> GameContext` 유지(현재 구현과 동일) |
| **nullable 규칙** | “없음 자체가 의미”면 nullable, 그 외는 기본값(0 또는 빈 리스트) |
| **meta 필드(핵심)** | `steam_id`, `generated_at`, `cc`, `lang`, `missing_appids`, `stale_appids` |
| **user 필드(방향)** | (현재) `behavior`(5) + (추가) `situational/play_style/sentiment/...`(1~4) |
| **games[appid] 필드(현재)** | `quality_trust`(6), `live`(7), `discount`(8) |
| **cc/lang 기본값** | **`us/en` 고정** |
| **범위 clamp** | `*_signal/_score/_ratio`는 **0~1**, `discount_percent`는 **0~100** |

### 5.2 Retrieval MVP: 후보 생성(POOL) 1차 기획안(권장)

| 항목 | 권장안 |
|---|---|
| **MVP 목표** | 유저가 후보를 주지 않아도 “그럴듯한” Top‑K가 나온다 |
| **이번 범위 제외(2차)** | 정교한 개인화/임베딩/FAISS |
| **Stage 1: 후보 풀(POOL)** | 입력: `config/appids.txt` (또는 `data/interim/candidate_pool/appids.json`) |
| **POOL 크기(초기)** | **1000** |
| **POOL 구성 원칙** | “Steam 상위 인기/대표 appid” 위주(팀이 합의한 리스트) |
| **Stage 2: Top‑K 점수화** | (6~8) 컨텍스트 점수 기반(현재 `topk_demo` 점수식으로 시작) |
| **Owned 정책(UX 분기)** | Discovery: 기본 **미보유만** / Rediscover: 옵션 “보유 중 장기 미접속” 섹션 |
| **고도화 경로** | 앵커 기반 확장(준‑개인화) → 임베딩/FAISS(정석) |

### 5.3 game_bundles 운영 정책(권장)

| 항목 | 권장안 |
|---|---|
| **기본 TTL** | 24h |
| **할인/가격 TTL** | 6~24h (`--ttl-hours`로 조절) |
| **missing/stale 발견 시(MVP)** | appid 스킵(빠른 응답) 또는 배치 재생성 큐에 넣기 |
| **대안(최신 우선)** | 요청 시점에 동기 on‑demand 재수집(비용/지연 증가) |
| **회의에서 결정 1개** | **빠른 응답 우선(스킵+백그라운드 보충)** vs **항상 최신(동기 보충)** |

### 5.4 MVP 성공 기준(권장)

| 항목 | 권장안 |
|---|---|
| **샘플 유저 수** | 3명 |
| **통과 조건(기술)** | `context_bundle` 생성/검증이 에러 없이 동작 |
| **통과 조건(기능)** | 후보 풀 1000개에서 Top‑K 10개가 출력 |
| **통과 조건(설명)** | reason이 납득 가능한 수준 |
| **운영 경고(추후)** | `missing_appids`, `stale_appids` 비율 기준은 추후 수치화 |

---

## 6) 다음 작업 제안(회의 후 바로 할 일)

회의에서 5.1~5.4의 “권장안”을 확정/수정한 뒤, 아래 순서로 바로 진행합니다.

| Step | 작업 | 산출물/완료 조건 |
|---:|---|---|
| 1 | 스키마 확정: context_bundle v0.1 고정 | 1~4의 `user.*` 자리/키 네이밍 + nullable/단위/clamp 규칙 확정 |
| 2 | 후보 풀 준비: POOL 파일 확정(초기 1000) | `config/appids.txt`를 SSOT로 두고 “왜 이 풀인지” 근거 문서화 |
| 3 | 대량 번들 생성/갱신 운영 | 후보 풀에 대해 (6~8) `game_bundles` 배치 준비 + TTL 정책 적용 |
| 4 | Retrieval MVP 구현(E2E) | 후보 풀 → context_bundle 조립 → Top‑K 출력 (초기 점수식은 `topk_demo`) |
| 5(선택) | 고도화 | 앵커 기반 확장 → 임베딩/FAISS → Phase 3 필터 연결 |

