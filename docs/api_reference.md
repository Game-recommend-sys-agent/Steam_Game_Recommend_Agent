# Steam API 레퍼런스 (프로젝트용 정리)

본 문서는 `GAME/API_조사.pdf` 내용을 바탕으로, **우리 프로젝트에서 실제로 쓰는 API/컬럼만** 작업하기 편한 형태로 재정리한 레퍼런스입니다.

---

## 1) 한눈에 보기: 우리가 주로 쓰는 것

- **조인 키(공통)**: `appid` (Steam 게임 고유 ID)
- **유저 행동(5)**: `IPlayerService.GetOwnedGames`의 `playtime_*`, `rtime_last_played`
- **게임 메타/필터(3~4)**: Store `appdetails` (가격/출시일/장르/언어/사양/연령/미디어/추천수)
- **완성도/신뢰도(6)**: `appreviews` 요약(`total_positive/total_reviews`) + `achievements.total` + `movies/screenshots/recommendations.total`
- **라이브(7)**: `ISteamNews.GetNewsForApp`의 `date/feedlabel/contents`
- **할인(8)**: `appdetails.price_overview.discount_percent` (+ price)

---

## 2) Steam Web API — 게임 & 유저 데이터

### 2.1 `ISteamApps.GetAppList` (게임 인덱스/변화 감지)

- **역할**: 전체 후보군 인덱스 + “최근 변경 감지” (가격/메타 변동 트리거)
- **주요 필드**
  - `response.apps[].appid` (🔥 모든 API 조인 키)
  - `response.apps[].name`
  - `response.apps[].last_modified` (최신성/변경 감지)
  - `response.apps[].price_change_number` (가격 변화 신호)
  - `response.have_more_results`, `response.last_appid` (페이징)

### 2.2 `IPlayerService.GetOwnedGames` (유저 실제 플레이 행동)

- **역할 요약**: “요즘 이 유저가 어떤 톤의 게임을 얼마나 했는가”
- **주요 필드**
  - `games[].appid`
  - `games[].name`
  - `games[].playtime_forever` (🔥 선호 강도 / 장기 신호) — **분 단위**
  - `games[].playtime_2weeks` (🔥 단기 취향 / 즉시성) — **분 단위**
  - `games[].rtime_last_played` (🔥 최신성 gate) — **Unix timestamp**
  - `games[].playtime_windows_forever / mac_forever / linux_forever` (환경)
  - `games[].playtime_deck_forever` (장치 컨텍스트)
  - `games[].has_community_visible_stats` (통계 공개 여부)

### 2.3 `ISteamUser.GetPlayerSummaries` (유저 상태/프로필)

- **용도**: 추천 성능보다는 **데이터 정합성/제약(공개 여부)** 확인용
- **주요 필드**
  - `players[].steamid`
  - `players[].personaname`, `avatar*` (UI)
  - `players[].communityvisibilitystate` (공개/비공개 제약)
  - `players[].personastate`, `lastlogoff` (활동성/타이밍)
  - `players[].timecreated` (숙련도 proxy)

---

## 3) ISteamUserStats — 업적/서사 텍스트(LLM 재료)

### 3.1 `ISteamUserStats.GetSchemaForGame`

- **역할 요약**: 캐릭터 관계/선택/세계관 톤을 유추할 수 있는 서사 신호
- **주요 필드**
  - `game.availableGameStats.achievements[]`
    - `displayName`, `description` (🔥 LLM 핵심 텍스트)
    - `hidden` (감정/비밀 요소)
    - `icon` (UI)
  - `game.availableGameStats.stats[]` (보조 통계)

> 5~8 구현에서 “완성도/밀도 proxy”로는 `achievements.total`(Store appdetails 쪽에도 존재) 또는 achievements 배열 길이를 사용합니다.

---

## 4) ISteamNews — 공식 업데이트/이벤트(라이브 신호)

### 4.1 `ISteamNews.GetNewsForApp`

- **역할 요약**: 신규 캐릭터, DLC, 스토리 확장을 알려주는 공식 텍스트(HTML)
- **주요 필드**
  - `appnews.count` (뉴스 개수)
  - `newsitems[].date` (🔥 최신성)
  - `newsitems[].feedlabel` (🔥 Update/Event 분류)
  - `newsitems[].contents` (🔥 LLM 핵심 텍스트, HTML)
  - `newsitems[].title`, `tags[]` (분위기/주제 보조)

---

## 5) Steam Store API — 게임 메타데이터(핵심 23개)

### 5.1 `GET https://store.steampowered.com/api/appdetails?appids={app_id}`

> PDF 기준 “총 160개 중 중요 23개” 위주.

#### 추천/필터에서 자주 쓰는 필드

- **식별**
  - `steam_appid`, `name`, `is_free`
- **가격/할인**
  - `price_overview.final` (현재 가격, 센트 단위)
  - `price_overview.discount_percent` (할인율)
- **장르/플레이 방식**
  - `genres[].description`
  - `categories[].description` (싱글/멀티/캐주얼 성향 등)
- **플랫폼**
  - `platforms.windows / mac / linux`
- **사양(텍스트)**
  - `pc_requirements.minimum` (최소 사양 텍스트)
- **컨트롤러**
  - `controller_support`
- **출시일**
  - `release_date.date` (문자열)
- **사회적 신뢰도/품질**
  - `recommendations.total`
  - `metacritic.score` (하한선으로만 참고)
- **설명(텍스트/HTML)**
  - `short_description`
  - `about_the_game`
  - `detailed_description` (🔥 매우 긴 텍스트/HTML, 톤 분석)
- **언어/연령**
  - `supported_languages` (HTML 포함 가능)
  - `required_age`
- **제작사/퍼블리셔**
  - `developers`, `publishers`
- **미디어**
  - `movies` (트레일러 존재/완성도 신호)
  - `screenshots` (시각적 준비 수준)
- **콘텐츠 디스크립터(회피 필터)**
  - `content_descriptors.ids`

#### 파싱 주의

- `supported_languages`, `detailed_description`, `newsitems[].contents` 등은 **HTML 포함** → 저장 시 raw를 보존하되, 추천 로직엔 **텍스트 정제본**도 함께 두는 게 안전.
- `price_overview`는 지역/통화/할인 조건에 따라 **누락** 가능 → 기본값 정책(없으면 0 또는 None) 필요.

---

## 6) Steam Review API — 리뷰 요약/개별 리뷰

### 6.1 `GET https://store.steampowered.com/appreviews/{app_id}?json=1`

#### 구현에서 “요약만” 써도 되는 핵심 필드

- `query_summary.total_positive`
- `query_summary.total_negative`
- `query_summary.total_reviews`
- `query_summary.review_score_desc` (Very Positive 등)

#### 개별 리뷰(선택)

- `reviews[].review` (본문 텍스트, 이탈/감정/캐릭터 분석)
- `reviews[].voted_up` (라벨)
- `reviews[].votes_up`, `weighted_vote_score` (가중치)
- `reviews[].language`
- `reviews[].author.playtime_forever`, `playtime_at_review` (초기 이탈/장기 만족)

> **주의(프로젝트 방향)**: 우리 프로젝트는 “탈-리뷰”를 기본으로 하므로, 추천의 주 입력으로 쓰기보다 **신뢰도/품질 보조 신호**로 한정하는 것을 권장.

---

## 7) 외부 데이터(선택)

- **Kaggle Steam dataset**: 빠른 콜드스타트/보조 통계에 유용할 수 있으나, 스키마 정합성/갱신 주기 이슈를 고려해 선택
- **Steam Community RSS**: PDF 코멘트 기준, 개발자 공지/패치 위주라 “업데이트 여부” 이상 활용이 어려움 → **비권장**
- **Game Wiki(Fandom 등)**: 로어/세계관 텍스트 확장용(선택). 정제/번역 비용 고려

---

## 8) Context-aware 5~8과의 매핑(바로 구현용)

| 모듈 | API | 필드(핵심) |
|---|---|---|
| (5) Behavior/Activity | `GetOwnedGames` | `playtime_2weeks`, `rtime_last_played`, `playtime_forever` |
| (6) Quality/Trust | Store `appdetails` | `movies`, `screenshots`, `recommendations.total`, `achievements.total` |
| (6) Quality/Trust | Review `appreviews` | `query_summary.total_positive`, `query_summary.total_reviews` |
| (7) Live | `GetNewsForApp` | `newsitems[].date`, `newsitems[].feedlabel`, `newsitems[].contents` |
| (8) Discount | Store `appdetails` | `price_overview.discount_percent` (+ `final`) |

---

## 9) 문서 위치(권장)

- **권장 파일**: `docs/api_reference.md` (현재 파일)
  - 이유: 워크플로우/컨텍스트/필터 등 여러 파트에서 공통으로 참조하는 “레퍼런스” 성격이 강함

