"use client";

import { useEffect, useMemo, useState } from "react";
import GameCard from "./GameCard";

type Game = {
  id: number;
  name: string;
  image: string;
  genres: string[];
  price: number;
};

type ImageRagResult = {
  rank: number;
  appid: number;
  game_name: string;
  score: number;
  image_url: string;
  image_caption: string;
  visual_summary: string;
  genres?: string;
  final_price_cents?: number;
};


type RecommendationResult = {
  ragResults?: ImageRagResult[];
  rankedGames?: any[];
  filteredGames?: any[];
  top3?: any[];
  [key: string]: any;
};

const API_BASE = "http://localhost:8000/api/v1";

const ITEMS_PER_PAGE = 5;

// Mock games removed, results now come from ragResults state

export default function SelectGamePage() {
  const [page, setPage] = useState(0);
  const [ragResults, setRagResults] = useState<ImageRagResult[] | null>(null);
  const [ragLoadError, setRagLoadError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("recommendation_result");
      console.log("[select-game] sessionStorage.recommendation_result raw:", raw);
      if (!raw) {
        setRagResults([]);
        return;
      }
      const parsed = JSON.parse(raw) as RecommendationResult;
      console.log("[select-game] parsed recommendation_result:", parsed);
      setRagResults(Array.isArray(parsed?.ragResults) ? parsed.ragResults : []);
    } catch (e: any) {
      setRagLoadError(e?.message ?? "Failed to load results");
      setRagResults([]);
    }
  }, []);

  // refetchImageRag removed as it was for debugging raw results

  /* 🔥 ragResults를 Game 타입으로 변환 */
  const games = useMemo(() => {
    if (!ragResults) return [];
    return ragResults.map((r: ImageRagResult) => {
      // API 응답의 genres 또는 visual_summary에서 추출
      const rawGenres = r.genres || (r.visual_summary && r.visual_summary.includes(",") ? r.visual_summary.split(",")[0] : "추천");
      const genresArray = typeof rawGenres === "string" 
        ? rawGenres.split(",").map((s: string) => s.trim()) 
        : ["추천"];
      
      return {
        id: r.appid,
        name: r.game_name || `App ${r.appid}`,
        image: r.image_url,
        genres: genresArray,
        price: r.final_price_cents !== undefined ? Math.floor(r.final_price_cents / 100) : 0
      };
    });
  }, [ragResults]);

  const totalPages = Math.max(1, Math.ceil(games.length / ITEMS_PER_PAGE));

  const startIndex = page * ITEMS_PER_PAGE;
  const currentGames = games.slice(
    startIndex,
    startIndex + ITEMS_PER_PAGE
  );

  // ragRawJson removed as it was for debugging

  const goPrev = () => {
    if (page > 0) setPage((prev) => prev - 1);
  };

  const goNext = () => {
    if (page < totalPages - 1) setPage((prev) => prev + 1);
  };

  return (
    <div className="page">
      {/* 🔥 여기 클래스 변경 */}
      <div className="select-container">
        <h1 className="title">
          우리 중 <span className="title-accent">누구</span>랑 놀래?
        </h1>

        {/* image-rag 리턴값 표시 (삭제됨) */}


        {/* 🔥 grid 래퍼 추가 (가로 폭 제어용) */}
        <div className="game-grid-wrapper">
          <div className="game-grid">
            {currentGames.map((game) => (
              <GameCard key={game.id} game={game} />
            ))}
          </div>
        </div>

        <div className="pagination">
          {page > 0 ? (
            <div
              className="triangle-btn triangle-left"
              onClick={goPrev}
            />
          ) : (
            <div style={{ width: 60 }} />
          )}

          <div className="page-indicator">
            {page + 1} / {totalPages}
          </div>

          {page < totalPages - 1 ? (
            <div
              className="triangle-btn triangle-right"
              onClick={goNext}
            />
          ) : (
            <div style={{ width: 60 }} />
          )}
        </div>
      </div>
    </div>
  );
}