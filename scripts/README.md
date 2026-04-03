# scripts/ — Phase 1 수집·전처리 스크립트

1차 스크래핑·API 호출 스크립트는 **여기(`scripts/`)** 에 두고, **데이터 수집**과 **추천 로직**은 분리합니다.

## 데이터 수집 전용 (스크래핑·API)

| 파일명 | 역할 | 비고 |
|--------|------|------|
| `fetch_steam_data.py` | Steam **Web API** (최근 플레이, 보유 게임, 앱 목록), **Store API** (appdetails), **IGDB** 메타데이터 | 추천 로직 없음. Kaggle·RSS 등은 별도 스크립트로 확장 예정. |
| `fetch_gamewiki.py` | **Fandom(GameWiki)** 게임 설명문 수집·파싱 (MediaWiki API). `FANDOM_WIKI_BASE`, `FANDOM_API_KEY`(선택) | `config/env.example` 참고. |
| `scrape_steam_store.py` | Steam **스토어** 검색 목록 스크래핑 (게임 목록, 출시일, 가격 등) | 팀 합의 시 추가 |
| `scrape_steam_full_sample.py` | 한 게임 **전체 샘플** (상세 페이지 + 리뷰 JSON) | 팀 합의 시 추가 |
| `scrape_steam_api.py` | Steam 공식 API 호출 래퍼·저장 (GetAppList, GetNewsForApp 등) | `fetch_steam_data.py`와 역할 구분 후 추가 가능 |

- **위치:** 위 파일들은 모두 **`scripts/`** 에 생성.
- **실행:** 프로젝트 루트에서 `python -m scripts.fetch_steam_data` 또는 `python scripts/fetch_steam_data.py` (환경 변수 설정 후).
- **GameWiki:**  
  - 한 게임: `python -m scripts.fetch_gamewiki "Elden Ring"` 또는 `--wiki minecraft` 등.  
  - **한국어 설명:** `--translate-to-ko` 또는 config 에 `"translate_to_ko": true` (deep-translator 사용).  
  - **config로 일괄:** `config/gamewiki_games.json` 에 `games`·`wiki_base`·`out_dir`·`translate_to_ko` 넣고 `python -m scripts.fetch_gamewiki --config` 실행.

## 추천 로직 (스크립트가 아님)

- 추천·컨텍스트·LLM 재랭킹은 **`src/game_recommendation/context_aware/baseline_recommender.py`** 에 있음.
- **실행 진입점:** 프로젝트 루트의 **`main.py`** (`python main.py`).

## 전처리 스크립트 (나중 단계)

- raw → processed 변환, 스키마 통일 등은 팀 합의 후 `scripts/preprocess_*.py` 등으로 추가하면 됩니다.
