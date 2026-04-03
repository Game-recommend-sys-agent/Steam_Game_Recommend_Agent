"""
Steam/Store/Review/News API 클라이언트.

목표:
- HTTP 호출부를 여기로 모으고, context-aware 로직에는 "데이터"만 전달
- 레이트리밋/재시도/타임아웃/캐시 정책을 한 곳에서 통제

구현 상세/저장 규칙은 `docs/context_aware_5to8.md` 참고.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class SteamClientConfig:
    # 네트워크/재시도
    timeout_s: float = 10.0
    max_retries: int = 4
    backoff_base_s: float = 0.7
    backoff_cap_s: float = 10.0

    # 레이트리밋(최소 간격, 초)
    min_interval_web_s: float = 0.25
    min_interval_store_s: float = 0.35

    # (7) News 기본 제한(권장)
    news_count: int = 20
    news_maxlength: int = 300


class _MinIntervalLimiter:
    def __init__(self, min_interval_s: float):
        self._min_interval_s = float(min_interval_s)
        self._next_allowed_at = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        if now < self._next_allowed_at:
            time.sleep(self._next_allowed_at - now)
        self._next_allowed_at = time.monotonic() + self._min_interval_s


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


class SteamClient:
    """
    - Steam Web API: api.steampowered.com (키 필요)
    - Steam Store API: store.steampowered.com (키 불필요)
    - Steam Review API(appreviews): store.steampowered.com (키 불필요)

    raw_dir 를 주면, 각 호출의 "원본 응답 JSON"을 2.7 규칙대로 저장한다.
    """

    WEB_BASE = "https://api.steampowered.com"
    STORE_BASE = "https://store.steampowered.com"

    def __init__(
        self,
        steam_api_key: str | None = None,
        *,
        raw_dir: str | Path | None = "data/raw",
        config: SteamClientConfig | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.steam_api_key = steam_api_key
        self.config = config or SteamClientConfig()
        self.raw_dir = Path(raw_dir) if raw_dir is not None else None

        self._web_limiter = _MinIntervalLimiter(self.config.min_interval_web_s)
        self._store_limiter = _MinIntervalLimiter(self.config.min_interval_store_s)

        self._http = http_client or httpx.Client(
            timeout=httpx.Timeout(self.config.timeout_s),
            headers={"User-Agent": "GAME/steam-client"},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SteamClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _request_json(
        self,
        *,
        base: str,
        path: str,
        params: dict[str, Any],
        limiter: _MinIntervalLimiter,
        method: str = "GET",
    ) -> Any:
        last_exc: Exception | None = None
        url = f"{base}{path}"

        for attempt in range(self.config.max_retries + 1):
            try:
                limiter.wait()
                resp = self._http.request(method, url, params=params)

                # 레이트리밋/서버 오류는 재시도(429, 5xx)
                if resp.status_code == 429 or 500 <= resp.status_code <= 599:
                    retry_after = resp.headers.get("retry-after")
                    if retry_after is not None:
                        try:
                            sleep_s = min(float(retry_after), self.config.backoff_cap_s)
                        except ValueError:
                            sleep_s = None
                    else:
                        sleep_s = None

                    if attempt < self.config.max_retries:
                        backoff = min(
                            self.config.backoff_cap_s,
                            self.config.backoff_base_s * (2**attempt),
                        )
                        jitter = random.uniform(0.0, 0.25 * backoff)
                        time.sleep((sleep_s if sleep_s is not None else backoff) + jitter)
                        continue

                resp.raise_for_status()
                return resp.json()
            except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError) as e:
                last_exc = e
                if attempt >= self.config.max_retries:
                    break
                backoff = min(
                    self.config.backoff_cap_s, self.config.backoff_base_s * (2**attempt)
                )
                jitter = random.uniform(0.0, 0.25 * backoff)
                time.sleep(backoff + jitter)

        assert last_exc is not None
        raise last_exc

    def _save_raw(self, path: Path, payload: Any) -> None:
        if self.raw_dir is None:
            return
        _atomic_write_json(self.raw_dir / path, payload)

    # (5) User signals
    def get_owned_games(self, steam_id: str) -> list[dict]:
        if not self.steam_api_key:
            raise ValueError("STEAM_API_KEY is required for Steam Web API calls.")
        payload = self._request_json(
            base=self.WEB_BASE,
            path="/IPlayerService/GetOwnedGames/v0001/",
            params={
                "key": self.steam_api_key,
                "steamid": steam_id,
                "include_appinfo": "true",
                "format": "json",
            },
            limiter=self._web_limiter,
        )
        self._save_raw(Path("owned_games") / f"{steam_id}.json", payload)
        return payload.get("response", {}).get("games", [])  # type: ignore[return-value]

    def get_recently_played_games(self, steam_id: str) -> list[dict]:
        if not self.steam_api_key:
            raise ValueError("STEAM_API_KEY is required for Steam Web API calls.")
        payload = self._request_json(
            base=self.WEB_BASE,
            path="/IPlayerService/GetRecentlyPlayedGames/v0001/",
            params={
                "key": self.steam_api_key,
                "steamid": steam_id,
                "format": "json",
            },
            limiter=self._web_limiter,
        )
        # 문서 2.7 raw 저장 목록에는 필수로 포함되지 않지만, 보조 입력이라 동일 규칙으로 저장
        self._save_raw(Path("recently_played_games") / f"{steam_id}.json", payload)
        return payload.get("response", {}).get("games", [])  # type: ignore[return-value]

    # (6) Quality/Trust
    def get_appdetails(self, appid: int, *, cc: str = "us", lang: str = "en") -> dict:
        payload = self._request_json(
            base=self.STORE_BASE,
            path="/api/appdetails",
            params={"appids": str(appid), "cc": cc, "l": lang},
            limiter=self._store_limiter,
        )
        self._save_raw(
            Path("appdetails") / f"{appid}__cc={cc}__lang={lang}.json", payload
        )
        return payload  # 원본 전체(앱ID 키 포함)를 그대로 반환

    def get_appreviews_summary(self, appid: int, *, lang: str = "all") -> dict:
        # 요약만 받기(MVP 강제): reviews[]를 받지 않도록 num_per_page=0
        payload = self._request_json(
            base=self.STORE_BASE,
            path=f"/appreviews/{appid}",
            params={
                "json": "1",
                "language": lang,
                "purchase_type": "all",
                "filter": "summary",
                "num_per_page": "0",
            },
            limiter=self._store_limiter,
        )
        self._save_raw(Path("appreviews_summary") / f"{appid}.json", payload)
        return payload

    def get_schema_for_game(self, appid: int) -> dict:
        if not self.steam_api_key:
            raise ValueError("STEAM_API_KEY is required for Steam Web API calls.")
        payload = self._request_json(
            base=self.WEB_BASE,
            path="/ISteamUserStats/GetSchemaForGame/v2/",
            params={"key": self.steam_api_key, "appid": str(appid), "format": "json"},
            limiter=self._web_limiter,
        )
        self._save_raw(Path("schema") / f"{appid}.json", payload)
        return payload

    # (7) Live
    def get_news_for_app(self, appid: int) -> dict:
        payload = self._request_json(
            base=self.WEB_BASE,
            path="/ISteamNews/GetNewsForApp/v0002/",
            params={
                "appid": str(appid),
                "count": str(self.config.news_count),
                "maxlength": str(self.config.news_maxlength),
                "format": "json",
            },
            limiter=self._web_limiter,
        )
        self._save_raw(Path("news") / f"{appid}.json", payload)
        return payload

