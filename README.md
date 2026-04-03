# 게임 추천 시스템 (Game Recommendation)

Steam 스토어/API 기반 게임 추천 시스템 프로젝트입니다.  
[진행 계획·워크플로우](docs/workflow.md)에 따라 Phase 0 → 6 순으로 진행합니다.

## 추천 아키텍처: Retrieval-first (Top-K), LLM은 후보 내에서만

유저 컨텍스트를 **LLM에 바로 보내지 않고**, ML 시스템·RAG 시스템처럼 **비교 가능한 구조**로 만듭니다.

1. **후보 풀 생성** — 컨텍스트·메타데이터(또는 임베딩)로 후보 게임 풀을 만든다.  
2. **Top-K Retrieval** — 그 풀에서 상위 K개를 선택한다. (모델·파라미터를 바꿔 가며 성능 비교 가능.)  
3. **(선택) Top-K 내에서만 LLM** — K개로 줄인 **후보**에 대해서만 LLM으로 비교·재랭킹·설명을 한다.  
   → “컨텍스트 → LLM → 추천”이 아니라 **“컨텍스트 → Retrieval(Top-K) → (선택) Top-K 내 LLM”** 구조.

## 현재 구현 범위(요약)

- **Context-aware 5~8 신호**: 유저 플레이/활동(Behavior), 게임 품질/신뢰(Quality/Trust), 라이브(News), 할인(Discount)
- **데이터 수집/캐시**: Steam Web API + Store `appdetails` + Review 요약 + News 수집 스크립트
- **번들/스냅샷 산출**: 컨텍스트 번들/게임 신호 번들/유저 행동 스냅샷 생성 스크립트
- **데모 실행**: `main.py`에서 “컨텍스트 생성 → 후보 생성/Top-K → (선택) LLM” 파이프라인 실행

## 기술 스택 (포트폴리오용)

| 구간 | 역할 | ML·LLM·툴 예시 |
|------|------|----------------|
| 후보 풀·Top-K | 검색·랭킹 | **ML:** 임베딩(sentence-transformers, OpenAI Embeddings), 유사도 검색(FAISS, Annoy), 협업/콘텐츠 필터 |
| Top-K 내 | 재랭킹·설명 | **LLM:** OpenAI/Claude API 또는 로컬 LLM (후보 메타만 입력) |
| Spec/Price | 필터·점수 | **ML:** 규칙 기반 점수, (선택) 회귀/분류 |

상세는 [docs/workflow.md §2.1](docs/workflow.md) 포트폴리오용 ML·LLM·툴 요약 표를 참고하면 됩니다.

## 디렉터리 구조

```
GAME/
├── config/                    # 설정(.env 예시 등)
│   └── env.example
├── data/                      # 수집·가공 데이터
│   ├── raw/                   # 원본 응답 캐시
│   │   └── owned_games/
│   ├── interim/               # 정규화/요약 산출물
│   │   └── user_games/
│   └── processed/             # 컨텍스트/스냅샷 산출물
│       └── user_behavior/
├── docs/                      # 문서
│   ├── workflow.md
│   ├── context_aware.md
│   ├── context_aware_5to8.md
│   └── api_reference.md
├── scripts/                   # 수집·전처리 스크립트
│   ├── build_game_signals_cache.py
│   ├── build_game_signals_bundle.py
│   ├── build_user_behavior_snapshot.py
│   ├── fetch_steam_data.py
│   ├── fetch_gamewiki.py
│   └── README.md
├── src/
│   └── game_recommendation/   # 추천 로직 패키지
│       ├── api/               # Steam API 클라이언트/래퍼
│       ├── context_aware/     # Phase 2: Context-aware
│       ├── personalization/   # Phase 3: Age/Popularity 슬라이더
│       ├── spec_aware/        # Phase 4: 사양 필터
│       └── price_aware/       # Phase 5: 할인·가성비
├── tests/                     # 테스트
├── main.py                    # 메인 진입점 (스크립트 수집 + 추천 파이프라인)
└── requirements.txt
```

자세한 구현/진행 흐름은 [docs/workflow.md](docs/workflow.md)와 `docs/context_aware_5to8.md`를 참고하세요.

## 시작하기

1. **환경**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **환경 변수(.env) 설정**
   - `config/env.example`를 복사해 **프로젝트 루트의 `.env`**(또는 `config/.env`)로 저장 후 실제 값으로 채웁니다.
   - `.env`는 `.gitignore`에 포함되어 **커밋되지 않습니다.**

   예시:

   ```bash
   cp config/env.example .env
   # 에디터로 .env 값을 채운 뒤 실행
   ```

3. **데이터 소스**
   - 스토어(Store) API: `store.steampowered.com` (키 없이도 호출 가능하지만 지역/제한에 따라 달라질 수 있음)
   - Steam Web API: `STEAM_API_KEY` 필요 (최근 플레이/보유 게임 등)
   - (선택) OpenAI: Top-K 내 재랭킹/설명에 사용 (`OPENAI_API_KEY`)

4. **실행(빠른 데모)**
   ```bash
   python main.py
   ```

5. **진행 순서**
   - [docs/workflow.md](docs/workflow.md) Phase 0 → 1(데이터 수집) → 2(Context-aware) → … → 6(통합·배포)

## 데이터/커밋 정책(중요)

- 이 프로젝트는 `data/raw`, `data/interim`, `data/processed` 아래에 **수집/가공 산출물(JSON 등)** 이 생성됩니다.
- 실무 운영을 가정해, 해당 산출물은 `.gitignore`로 **커밋에서 제외**하고 폴더 구조 유지를 위한 `.gitkeep`만 추적합니다.
- 즉, GitHub에는 **코드/문서/설정 템플릿만 올리고**, 데이터는 각자 로컬에서 생성하는 방식입니다.

## 팀 작업

- 브랜치 전략·코드 리뷰 규칙은 팀 내 합의 후 `docs/` 에 정리해 두면 됩니다.
- 데이터 파일은 커밋하지 않는 것을 기본으로 하며, 팀 공유가 필요하면 별도 스토리지/정책을 권장합니다.
