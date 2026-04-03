"""
Steam / IGDB 데이터 수집 전용 스크립트.

- Steam Web API: 최근 플레이, 보유 게임, 앱 목록
- Steam Store API: 앱 상세(appdetails)
- IGDB API: 게임 메타데이터(장르, 테마, 모드, 평점)

다른 데이터 소스(Kaggle, Steam Community RSS 등)는 별도 스크립트로 확장 예정.
"""
import json
import requests


# ---------------------------------------------------------------------------
# Steam Web API
# ---------------------------------------------------------------------------

def get_recent_games(steam_api_key: str, steam_id: str) -> list:
    """Steam Web API: 최근 플레이한 게임 목록."""
    url = "http://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v0001/"
    params = {"key": steam_api_key, "steamid": steam_id, "format": "json"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("response", {}).get("games", [])


def get_owned_games(steam_api_key: str, steam_id: str) -> list:
    """Steam Web API: 보유 게임 목록 (앱 정보 포함)."""
    url = "http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
    params = {
        "key": steam_api_key,
        "steamid": steam_id,
        "include_appinfo": True,
        "format": "json",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("response", {}).get("games", [])


def get_app_list(limit: int = 200) -> list:
    """Steam Web API: 앱 목록 (GetAppList). API 키 불필요."""
    url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError):
        return []
    apps = data.get("applist", {}).get("apps", [])
    return apps[:limit]


# ---------------------------------------------------------------------------
# Steam Store API (appdetails)
# ---------------------------------------------------------------------------

def get_game_details(appid: int, cc: str = "us", lang: str = "en") -> dict | None:
    """Steam Store API: 앱 상세 정보 (장르, 카테고리, 플레이타임 등)."""
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc={cc}&l={lang}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError, KeyError):
        return None

    entry = data.get(str(appid), {})
    if not entry.get("success"):
        return None

    raw = entry.get("data", {})
    if not raw.get("name"):
        return None

    genres = [g["description"] for g in raw.get("genres", [])]
    categories = [c["description"] for c in raw.get("categories", [])]
    avg_playtime = raw.get("playtime_forever", 0)
    difficulty = "Challenging" if "Difficult" in categories else "Moderate"
    mode = "Single player" if "Single-player" in categories else "Multiplayer"
    name_lower = raw.get("name", "").lower()
    theme = (
        "Fantasy"
        if any(t in name_lower for t in ["dragon", "fantasy", "magic"])
        else None
    )

    return {
        "appid": appid,
        "name": raw.get("name"),
        "genres": genres,
        "avg_playtime": avg_playtime,
        "difficulty": difficulty,
        "mode": mode,
        "theme": theme,
    }


# ---------------------------------------------------------------------------
# IGDB API (게임 메타데이터)
# ---------------------------------------------------------------------------

def get_igdb_token(client_id: str, client_secret: str) -> str:
    """IGDB(Twitch) OAuth2 토큰 발급."""
    resp = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_game_metadata_igdb(
    game_name: str,
    client_id: str,
    client_secret: str,
    *,
    _token: str | None = None,
) -> dict:
    """IGDB: 게임 메타데이터 (장르, 테마, 모드, 평점)."""
    token = _token or get_igdb_token(client_id, client_secret)
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }
    query = f"""
    fields
        genres.name,
        themes.name,
        game_modes.name,
        player_perspectives.name,
        total_rating;
    where name ~ "{game_name}"*;
    limit 1;
    """
    resp = requests.post(
        "https://api.igdb.com/v4/games",
        headers=headers,
        data=query,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data[0] if data else {}


if __name__ == "__main__":
    # 사용 예: API 키는 환경 변수 등으로 주입 권장
    import os

    steam_key = os.environ.get("STEAM_API_KEY", "")
    steam_id = os.environ.get("STEAM_ID", "")
    if steam_key and steam_id:
        recent = get_recent_games(steam_key, steam_id)
        print("최근 플레이:", len(recent), "개")
    apps = get_app_list(limit=5)
    print("앱 목록 샘플:", len(apps), "개")
