"""
Fandom(GameWiki) 게임 설명문 수집·파싱 스크립트.

- MediaWiki API 사용 (Fandom은 대부분 읽기용 API 키 불필요).
- 게임 이름으로 위키 검색 → 해당 문서 인트로(설명문) 추출.
- 한국어: 위키 한국어 URL(lang=ko) 시도 후, 없으면 번역(deep-translator)으로 한국어 출력.
- 선택: FANDOM_API_KEY 가 있으면 헤더에 넣어 요청 (일부 위키/파트너 정책 대응).

사용 예:
  python -m scripts.fetch_gamewiki "Elden Ring" --translate-to-ko
  python -m scripts.fetch_gamewiki --config   # config 에 translate_to_ko: true 가능
"""
import argparse
import json
import os
import re
import time
from pathlib import Path

import requests

try:
    from deep_translator import GoogleTranslator
    _HAS_TRANSLATOR = True
except ImportError:
    _HAS_TRANSLATOR = False

# Fandom은 적절한 User-Agent 요청 권장 (봇 정책)
DEFAULT_USER_AGENT = (
    "GameRecommendationBot/1.0 (Game recommendation project; contact: optional)"
)


def _translate_to_ko(text: str, max_chunk: int = 4500) -> str:
    """영문(등) 설명문을 한국어로 번역. deep-translator 미설치 시 원문 반환."""
    if not text or not text.strip():
        return text
    if not _HAS_TRANSLATOR:
        return text
    try:
        # 긴 텍스트는 청크로 나눠 번역 후 이어붙임 (Google 제한 대략 5000자)
        out = []
        for i in range(0, len(text), max_chunk):
            chunk = text[i : i + max_chunk]
            if not chunk.strip():
                continue
            t = GoogleTranslator(source="auto", target="ko").translate(chunk)
            if t:
                out.append(t)
        return "\n".join(out) if out else text
    except Exception:
        return text


def get_game_description(
    game_name: str,
    wiki_base: str = "videogaming",
    *,
    api_key: str | None = None,
    user_agent: str | None = None,
    max_chars: int = 2000,
    timeout: int = 15,
    lang: str | None = None,
    translate_to_ko: bool = False,
) -> dict:
    """
    게임 이름으로 Fandom 위키 검색 후 해당 문서의 인트로(설명문) 추출.

    Args:
        game_name: 검색할 게임 이름
        wiki_base: Fandom 위키 서브도메인 (예: videogaming → videogaming.fandom.com, 게임별: eldenring, minecraft)
        api_key: 선택. Fandom/파트너 API 키 (있으면 헤더에 전달)
        user_agent: 선택. User-Agent (없으면 기본값)
        max_chars: 추출할 최대 문자 수
        timeout: 요청 타임아웃(초)
        lang: 위키 언어 (예: "ko" → /ko/api.php). None 이면 기본(영문) URL.
        translate_to_ko: True 이면 가져온 설명을 한국어로 번역(deep-translator).

    Returns:
        {"game_name": str, "wiki_base": str, "page_title": str | None,
         "description": str, "url": str | None, "error": str | None, "description_lang": str}
    """
    path_prefix = f"/{lang}" if lang else ""
    base_url = f"https://{wiki_base}.fandom.com{path_prefix}/api.php"
    headers = {"User-Agent": user_agent or DEFAULT_USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        # 일부 API는 X-API-Key 사용
        headers["X-API-Key"] = api_key

    result = {
        "game_name": game_name,
        "wiki_base": wiki_base,
        "page_title": None,
        "description": "",
        "url": None,
        "error": None,
    }

    # 1) 검색으로 페이지 제목 찾기
    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": game_name,
        "srlimit": 5,
        "format": "json",
    }
    try:
        r = requests.get(
            base_url,
            params=search_params,
            headers=headers,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        result["error"] = f"search request failed: {e}"
        return result
    except ValueError as e:
        result["error"] = f"search json error: {e}"
        return result

    search_list = data.get("query", {}).get("search", [])
    if not search_list:
        result["error"] = "no search results"
        return result

    # 첫 번째 검색 결과 페이지 제목 사용
    page_title = search_list[0].get("title", "")
    if not page_title:
        result["error"] = "empty page title"
        return result

    result["page_title"] = page_title

    # 2) 해당 페이지 인트로(설명) 추출 (TextExtracts 확장 사용)
    # exintro=1: 첫 섹션만, explaintext=1: HTML 제거 플레인 텍스트
    extract_params = {
        "action": "query",
        "prop": "extracts",
        "titles": page_title,
        "exintro": 1,
        "explaintext": 1,
        "exchars": max_chars,
        "format": "json",
    }
    try:
        r2 = requests.get(
            base_url,
            params=extract_params,
            headers=headers,
            timeout=timeout,
        )
        r2.raise_for_status()
        data2 = r2.json()
    except requests.RequestException as e:
        result["error"] = f"extract request failed: {e}"
        return result
    except ValueError as e:
        result["error"] = f"extract json error: {e}"
        return result

    pages = data2.get("query", {}).get("pages", {})
    # page id 키는 숫자 또는 "-1" (없음)
    page_id = next(iter(pages)) if pages else None
    if not page_id or page_id == "-1":
        result["error"] = "page not found"
        return result

    extract = pages.get(str(page_id), {}).get("extract", "")
    if not extract or not extract.strip():
        # TextExtracts 미지원 위키: revisions 로 원문 가져와서 위키 문법 제거
        extract = _fetch_via_revisions(
            base_url, page_title, page_id, headers, timeout, max_chars
        )
        if not extract or not extract.strip():
            result["error"] = "empty extract (wiki may not support TextExtracts, and revisions fallback yielded nothing)"
            return result

    # 1차 파싱: 과도한 공백/줄바꿈 정리
    description = re.sub(r"\n{3,}", "\n\n", extract.strip())
    description = re.sub(r" +", " ", description)

    # 한국어 출력: translate_to_ko 이면 번역 (위키 한국어 URL만으로 부족할 때 대비)
    if translate_to_ko and description:
        description = _translate_to_ko(description)
        result["description_lang"] = "ko"
    else:
        result["description_lang"] = lang or "en"

    result["description"] = description
    result["url"] = f"https://{wiki_base}.fandom.com{path_prefix}/wiki/{page_title.replace(' ', '_')}"

    return result


def _strip_wikitext(raw: str, max_chars: int = 2000) -> str:
    """위키 문법을 단순 제거해 읽기 쉬운 텍스트로 만든다."""
    if not raw or not raw.strip():
        return ""
    text = raw[: max_chars * 2]
    # [[link]] or [[link|label]] → label or link
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    # '''bold''', ''italic'' 제거
    text = re.sub(r"'{2,3}([^']*)'{2,3}", r"\1", text)
    # {{template}} 제거
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text)
    return text.strip()[:max_chars]


def _fetch_via_revisions(
    base_url: str,
    page_title: str,
    page_id,
    headers: dict,
    timeout: int,
    max_chars: int,
) -> str:
    """prop=revisions 로 본문 가져와서 위키 문법 제거 후 반환."""
    rev_params = {
        "action": "query",
        "prop": "revisions",
        "titles": page_title,
        "rvprop": "content",
        "rvlimit": 1,
        "format": "json",
    }
    try:
        r2 = requests.get(base_url, params=rev_params, headers=headers, timeout=timeout)
        r2.raise_for_status()
        data2 = r2.json()
    except (requests.RequestException, ValueError):
        return ""
    pages_data = data2.get("query", {}).get("pages", {})
    revs = pages_data.get(str(page_id), {}).get("revisions", [])
    if not revs:
        return ""
    content = revs[0].get("*", "")
    return _strip_wikitext(content, max_chars)


def fetch_and_save(
    game_name: str,
    wiki_base: str,
    out_dir: Path,
    *,
    api_key: str | None = None,
    lang: str | None = None,
    translate_to_ko: bool = False,
) -> dict:
    """설명문 조회 후 out_dir 에 JSON으로 저장."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = get_game_description(
        game_name,
        wiki_base,
        api_key=api_key,
        lang=lang,
        translate_to_ko=translate_to_ko,
    )
    safe_name = re.sub(r"[^\w\s-]", "", game_name).strip()[:80]
    safe_name = re.sub(r"[-\s]+", "_", safe_name) or "unknown"
    out_path = out_dir / f"gamewiki_{safe_name}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    data["_saved_path"] = str(out_path)
    return data


def load_games_config(config_path: Path) -> dict:
    """
    config JSON 로드.
    형식: { "games": ["이름", ...] 또는 [{"name": "...", "wiki": "..."}, ...], "wiki_base": "...", "out_dir": "..." }.
    게임이 문자열이면 wiki_base 사용; {"name", "wiki"} 객체면 해당 게임만 그 위키 사용.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw_games = data.get("games", [])
    if not raw_games:
        raise ValueError("config must have non-empty 'games' list")
    default_wiki = data.get("wiki_base", os.environ.get("FANDOM_WIKI_BASE", "videogaming"))
    games = []
    for g in raw_games:
        if isinstance(g, str):
            games.append({"name": g.strip(), "wiki": default_wiki})
        elif isinstance(g, dict) and g.get("name"):
            games.append({"name": g["name"].strip(), "wiki": g.get("wiki", default_wiki)})
        else:
            continue
    if not games:
        raise ValueError("config 'games' had no valid entries")
    return {
        "games": games,
        "out_dir": data.get("out_dir", os.environ.get("GAMEWIKI_OUT_DIR", "data/raw")),
        "lang": data.get("lang"),
        "translate_to_ko": bool(data.get("translate_to_ko", False)),
    }


def main():
    root = Path(__file__).resolve().parent.parent
    default_config = root / "config" / "gamewiki_games.json"

    parser = argparse.ArgumentParser(description="Fandom(GameWiki) 게임 설명문 수집")
    parser.add_argument(
        "game_name",
        nargs="?",
        default=None,
        help="검색할 게임 이름 (한 개). 생략 시 --config 필요.",
    )
    parser.add_argument(
        "--config",
        nargs="?",
        const=str(default_config),
        default=None,
        metavar="PATH",
        help=f"게임 목록 config 파일 경로 (JSON). 생략 시 기본: config/gamewiki_games.json. 이 옵션만 주면 config 목록 일괄 수집.",
    )
    parser.add_argument(
        "--wiki",
        default=os.environ.get("FANDOM_WIKI_BASE", "videogaming"),
        help="Fandom 위키 서브도메인 (기본: videogaming). 게임별 위키 예: eldenring, minecraft",
    )
    parser.add_argument(
        "--out-dir",
        default=os.environ.get("GAMEWIKI_OUT_DIR", "data/raw"),
        help="저장 디렉터리 (기본: data/raw)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="저장하지 않고 stdout 에만 출력",
    )
    parser.add_argument(
        "--translate-to-ko",
        action="store_true",
        help="가져온 설명을 한국어로 번역 (deep-translator 사용)",
    )
    parser.add_argument(
        "--lang",
        default=None,
        metavar="CODE",
        help="위키 언어 코드 (예: ko → 한국어 위키 URL 시도). 번역은 --translate-to-ko 사용",
    )
    args = parser.parse_args()

    api_key = os.environ.get("FANDOM_API_KEY") or None

    # ----- config 로 일괄 수집 -----
    if args.config is not None:
        config_path = root / args.config if not os.path.isabs(args.config) else Path(args.config)
        try:
            cfg = load_games_config(config_path)
        except (FileNotFoundError, ValueError) as e:
            print("Error:", e)
            return
        out_dir = root / cfg["out_dir"]
        out_dir.mkdir(parents=True, exist_ok=True)
        lang = cfg.get("lang")
        translate_to_ko = cfg.get("translate_to_ko", False)
        for i, item in enumerate(cfg["games"]):
            name = item["name"]
            wiki_base = item["wiki"]
            if not name:
                continue
            print(f"[{i+1}/{len(cfg['games'])}] {name} (wiki={wiki_base}, ko={translate_to_ko})")
            result = fetch_and_save(
                name,
                wiki_base,
                out_dir,
                api_key=api_key,
                lang=lang,
                translate_to_ko=translate_to_ko,
            )
            if result.get("error"):
                print("  Error:", result["error"])
            else:
                print("  Saved:", result.get("_saved_path", ""))
            if i < len(cfg["games"]) - 1:
                time.sleep(0.5)  # 요청 간격
        return

    # ----- 게임 이름 한 개 (기존 동작) -----
    if not args.game_name:
        parser.print_help()
        print("\n예: 게임 이름 한 개 → python -m scripts.fetch_gamewiki \"Elden Ring\"")
        print("    config 목록 일괄 → python -m scripts.fetch_gamewiki --config")
        return

    if args.no_save:
        result = get_game_description(
            args.game_name,
            args.wiki,
            api_key=api_key,
            lang=args.lang,
            translate_to_ko=args.translate_to_ko,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    out_dir = root / args.out_dir
    result = fetch_and_save(
        args.game_name,
        args.wiki,
        out_dir,
        api_key=api_key,
        lang=args.lang,
        translate_to_ko=args.translate_to_ko,
    )
    if result.get("error"):
        print("Error:", result["error"])
    else:
        print("Saved:", result.get("_saved_path", ""))
        print("Description (first 300 chars):", (result.get("description") or "")[:300])


if __name__ == "__main__":
    main()
