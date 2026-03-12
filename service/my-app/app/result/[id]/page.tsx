"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import GameCard, { Game } from "../../select-game/GameCard";

/* 임시 mock */
// Mock games removed, results now come from sessionStorage


function formatPrice(price: number) {
  return price === 0 ? "무료" : `₩ ${price.toLocaleString()}`;
}

export default function ResultDetailPage() {
  const router = useRouter();
  const params = useParams();
  const routeId = Number(params?.id ?? 0);

  const [games, setGames] = useState<Game[]>([]);

  useMemo(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = sessionStorage.getItem("recommendation_result");
      if (raw) {
        const parsed = JSON.parse(raw);
        const ragResults = Array.isArray(parsed?.ragResults) ? parsed.ragResults : [];
        const transformed: Game[] = ragResults.map((r: any) => {
          const rawGenres = r.genres || (r.visual_summary && r.visual_summary.includes(",") ? r.visual_summary.split(",")[0] : "추천");
          const genresArray = typeof rawGenres === "string" 
            ? rawGenres.split(",").map((s: string) => s.trim()) 
            : ["추천"];
          
          return {
            id: r.appid,
            name: r.game_name || `App ${r.appid}`,
            image: r.image_url,
            genres: genresArray,
            price: r.final_price_cents !== undefined ? Math.floor(r.final_price_cents / 100) : 0,
            os: "전체",
            steamUrl: `https://store.steampowered.com/app/${r.appid}`
          };
        });
        setGames(transformed);
      }
    } catch (e) {
      console.error("Failed to loadDetail data", e);
    }
  }, []);

  const activeGame = useMemo(() => {
    return games.find((g) => g.id === routeId) || games[0];
  }, [games, routeId]);

  const extraGames = useMemo(() => {
    if (!activeGame) return [];
    return games
      .filter((g) => g.id !== activeGame.id)
      .slice(0, 2);
  }, [games, activeGame]);

  const handleGoSteam = () => {
    const url =
      activeGame.steamUrl ?? "https://store.steampowered.com/";
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="page">
      <div className="select-container">

        {/* 🔁 Restart Bubble */}
        <button
          className="restart-bubble"
          onClick={() => router.push("/")}
        >
          처음부터 다시 해 볼래?
        </button>

        <div className="result-layout">

          {/* ================= LEFT ================= */}
          <section className="result-left">

            <div className="main-title-box">
              {activeGame ? `${activeGame.name} - 부담없이 가볍게 같이 놀기 좋은 친구야` : "추천 친구를 찾는 중..."}
            </div>

            <div
              className="main-frame clickable"
              onClick={handleGoSteam}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ")
                  handleGoSteam();
              }}
            >
            {activeGame && (
              <>
                <div className="main-poster">
                  <img
                    src={activeGame.image}
                    alt={activeGame.name}
                    draggable={false}
                  />
                </div>
              </>
            )}
            </div>

            {activeGame && (
              <>
                <div className="main-meta-box">
                  <div className="main-meta-row">
                    <div className="meta-pill">
                      {activeGame.genres.slice(0, 2).join(" · ")}
                    </div>
                    <div className="meta-pill">
                      {formatPrice(activeGame.price)}
                    </div>
                    <div className="meta-pill">
                      {activeGame.os}
                    </div>
                  </div>
                </div>

                <button
                  className="main-play-btn"
                  onClick={handleGoSteam}
                >
                  이 친구랑 놀기 →
                </button>
              </>
            )}


          </section>

          {/* ================= RIGHT ================= */}
          <aside className="result-right">

            <div className="side-header-box">
              이 친구는 어때?
            </div>

            {extraGames.length > 0 ? (
              <div className="game-grid">
                {extraGames.map((g) => (
                  <GameCard key={g.id} game={g} />
                ))}
              </div>
            ) : (
              <div style={{ opacity: 0.6, padding: 20 }}>비슷한 친구들을 더 찾고 있어요.</div>
            )}

          </aside>

        </div>
      </div>
    </div>
  );
}