"use client";

import { useRouter } from "next/navigation";

export type Game = {
  id: number;
  name: string;
  image: string;
  genres: string[];
  price: number;
  os?: string;          // 🔥 추가 (optional)
  steamUrl?: string;
};

export default function GameCard({ game }: { game: Game }) {
  const router = useRouter();

  const handleClick = () => {
    router.push(`/result/${game.id}`);
  };

  return (
    <div
      className="game-card"
      onClick={handleClick}
      role="button"
      tabIndex={0}
    >
      {/* 🔥 포스터 영역 (여백 포함) */}
      <div className="poster-wrapper">
        <div className="poster">
          <img
            src={game.image}
            alt={game.name}
            draggable={false}
          />
        </div>
      </div>

      <div className="card-body">
        <div className="card-title">{game.name}</div>

        <div className="genre-pill">
          {game.genres.slice(0, 2).join(" · ")}
        </div>

        <div className="card-price">
          {game.price === 0
            ? "무료"
            : `₩${game.price.toLocaleString()}`}
        </div>
      </div>
    </div>
  );
}