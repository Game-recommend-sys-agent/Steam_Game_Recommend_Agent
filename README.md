# 게임 추천 시스템 (Game Recommendation)

Steam 스토어/API 기반 게임 추천 시스템 프로젝트입니다.  
<br>
<img width="182" height="142" alt="steam rec" src="https://github.com/user-attachments/assets/1334714b-2693-4e9e-b214-69e63cf8441f" />  
<br>
전략 문서(전략.pdf)와 [진행 계획·워크플로우](docs/workflow.md)에 따라 Phase 0 → 6 순으로 진행합니다.

## 추천 아키텍처: Retrieval-first (Top-K), LLM은 후보 내에서만

유저 컨텍스트를 **LLM에 바로 보내지 않고**, ML 시스템·RAG 시스템처럼 **비교 가능한 구조**로 만듭니다.

1. **후보 풀 생성** — 컨텍스트·메타데이터(또는 임베딩)로 후보 게임 풀을 만든다.  
2. **Top-K Retrieval** — 그 풀에서 상위 K개를 선택한다. (모델·파라미터를 바꿔 가며 성능 비교 가능.)  
3. **(선택) Top-K 내에서만 LLM** — K개로 줄인 **후보**에 대해서만 LLM으로 비교·재랭킹·설명을 한다.  
   → “컨텍스트 → LLM → 추천”이 아니라 **“컨텍스트 → Retrieval(Top-K) → (선택) Top-K 내 LLM”** 구조.

## 기술 스택 (포트폴리오용)

| 구간 | 역할 | ML·LLM·툴 예시 |
|------|------|----------------|
| 후보 풀·Top-K | 검색·랭킹 | **ML:** 임베딩(sentence-transformers, OpenAI Embeddings), 유사도 검색(FAISS, Annoy), 협업/콘텐츠 필터 |
| Top-K 내 | 재랭킹·설명 | **LLM:** OpenAI/Claude API 또는 로컬 LLM (후보 메타만 입력) |
| Spec/Price | 필터·점수 | **ML:** 규칙 기반 점수, (선택) 회귀/분류 |

상세는 [docs/workflow.md §2.1](docs/workflow.md) 포트폴리오용 ML·LLM·툴 요약 표를 참고하면 됩니다.

## 디렉터리 구조

```
game/
├── config/              # 설정, 스키마 예시
├── data/                # 수집·가공 데이터 (raw / processed / interim)
├── docs/                # 문서 (workflow, 스키마, 수집 가능 컬럼 등)
├── scripts/             # 수집·전처리 스크립트 (스토어 스크래핑, API 호출 등)
├── src/
│   └── game_recommendation/   # 추천 로직 패키지
│       ├── context_aware/     # Phase 2: Context-aware
│       ├── personalization/   # Phase 3: Age/Popularity 슬라이더
│       ├── spec_aware/        # Phase 4: 사양 필터
│       ├── price_aware/       # Phase 5: 할인·가성비
│       └── api/               # Phase 6: 추천 API
├── tests/               # 테스트
├── baseline.py          # 베이스라인/실험 스크립트
├── requirements.txt
└── 전략.pdf
```

자세한 역할은 [docs/DIRECTORY.md](docs/DIRECTORY.md)를 참고하세요.

## 시작하기

1. **환경**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **데이터 소스**
   - 스토어 스크래핑: `store.steampowered.com` (API 키 불필요)
   - 공식 API: `STEAM_API_KEY` 환경 변수 설정 후 사용

3. **진행 순서**
   - [docs/workflow.md](docs/workflow.md) Phase 0 → 1(데이터 수집) → 2(Context-aware) → … → 6(통합·배포)

## 팀 작업

- 브랜치 전략·코드 리뷰 규칙은 팀 내 합의 후 `docs/` 에 정리해 두면 됩니다.
- 데이터 파일(`data/raw`, `data/processed`)은 `.gitignore` 로 제외되어 있을 수 있으므로, 대용량·공유 데이터는 별도 저장소/스토리지 정책을 권장합니다.
