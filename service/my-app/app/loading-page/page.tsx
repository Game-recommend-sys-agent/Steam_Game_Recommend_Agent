"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";

const API_BASE = "http://localhost:8000/api/v1";

/* ─────────────────────────────────────────────────────────
   단계 정의
   done  = API 응답 수신 후 점등
   active = 현재 호출 중 (점이 깜빡임)
───────────────────────────────────────────────────────── */
const steps = [
  { icon: "👀", text: "어디서 놀 수 있는지 먼저 살펴보는 중…" },
  { icon: "💻", text: "무리 없이 즐길 수 있는지 살짝 체크 중이야" },
  { icon: "✨", text: "분위기랑 장르가 잘 맞는지 비교하고 있어" },
  { icon: "🔍", text: "느낌이 비슷한 캐릭터를 발견했어!" },
];

/* ─────────────────────────────────────────────────────────
   타입
───────────────────────────────────────────────────────── */
interface RecommendationState {
  steamId: string;
  prompt: string;
  age: number | null;
  price: string | null;
  os: string | null;
  spec: string | null;
  genres: string[];
}

interface FilteredGame {
  game_id: number;
  game_name: string;
  image_url?: string;
  genres?: string;
  final_price_cents?: number;
  [key: string]: any;
}

interface ImageRagResult {
  rank: number;
  appid: number;
  game_name: string;
  score: number;
  image_url: string;
  image_caption: string;
  visual_summary: string;
}

export default function LoadingPage() {
  const router = useRouter();

  /* 0~3: 완료된 스텝 수 (currentStep 미만은 done, currentStep은 active) */
  const [currentStep, setCurrentStep] = useState(0);
  const [allDone, setAllDone] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fetchedRef = useRef(false);

  /* 결과는 sessionStorage에 저장 후 결과 페이지에서 읽음 */
  useEffect(() => {
    console.log("[loading-page] useEffect mounted, fetchedRef.current:", fetchedRef.current);
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    runPipeline();
    return () => {
      console.log("[loading-page] useEffect unmounted");
    };
  }, []);

  async function runPipeline() {
    /* ── 세션스토리지에서 사용자 입력 복원 ── */
    let state: RecommendationState = {
      steamId: "",
      prompt: "",
      age: null,
      price: null,
      os: null,
      spec: null,
      genres: [],
    };
    try {
      const raw = sessionStorage.getItem("recommendation_state");
      if (raw) state = JSON.parse(raw);
    } catch {}

    try {
      /* ══════════════════════════════════════════
         STEP 0 — /recommend/filter  (필터링)
      ══════════════════════════════════════════ */
      const filterBody: Record<string, any> = { limit: 50 };
      if (state.os)     filterBody.os     = state.os;
      if (state.age)    filterBody.age    = state.age;
      if (state.price)  filterBody.price  = state.price;
      if (state.spec)   filterBody.spec   = state.spec;
      if (state.genres?.length) filterBody.genres = state.genres;

      console.log("[loading-page] Starting STEP 0 - /recommend/filter API call", filterBody);
      const filterRes = await fetch(`${API_BASE}/recommend/filter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(filterBody),
      });
      console.log("[loading-page] STEP 0 response status:", filterRes.status);
      if (!filterRes.ok) throw new Error(`filter API ${filterRes.status} - ${await filterRes.text()}`);
      const filterData = await filterRes.json();
      const filteredGames: FilteredGame[] = filterData.results ?? [];
      console.log("[loading-page] filter results count:", filteredGames.length);

      setCurrentStep(1); // step 0 done → step 1 active

      /* ══════════════════════════════════════════
         STEP 1a — /context/user  (유저 컨텍스트 추출)
      ══════════════════════════════════════════ */
      console.log("[loading-page] Starting STEP 1a - /context/user API call");
      const userCtxRes = await fetch(`${API_BASE}/context/user`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          steam_id: state.steamId || "",
          mood_tag: state.prompt || "",
          owned_rows: [],
          include_sentiment: false,
          include_situational: true,
          include_play_style: true,
        }),
      });
      console.log("[loading-page] STEP 1a response status:", userCtxRes.status);
      if (!userCtxRes.ok) throw new Error(`context/user API ${userCtxRes.status} - ${await userCtxRes.text()}`);
      const userContext = await userCtxRes.json();
      console.log("[loading-page] user context:", userContext);

      /* ══════════════════════════════════════════
         STEP 1 — /recommend/llm-topk  (LLM 필터링)
      ══════════════════════════════════════════ */
      const llmRes = await fetch(`${API_BASE}/recommend/llm-topk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filtered_games: filteredGames,
          user_context: userContext,
          steam_id: state.steamId,
          top_k: 30,
        }),
      });
      if (!llmRes.ok) throw new Error(`llm-topk API ${llmRes.status}`);
      const llmData = await llmRes.json();
      const rankedGames = llmData.ranked_games ?? [];
      console.log("[loading-page] llm-topk ranked_games count:", rankedGames.length);

      setCurrentStep(2); // step 1 done → step 2 active

      /* ══════════════════════════════════════════
         STEP 2 — /recommend/image-rag  (캐릭터 RAG)
      ══════════════════════════════════════════ */
      const ragAppids: number[] = rankedGames
        .map((g: any) => g.game_id)
        .filter((id: any) => typeof id === "number");

      const ragRes = await fetch(`${API_BASE}/recommend/image-rag`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_input: state.prompt || "추천 게임",
          appids: ragAppids.length > 0 ? ragAppids : null,
          top_k: 30,
        }),
      });
      if (!ragRes.ok) throw new Error(`image-rag API ${ragRes.status}`);
      const ragData = await ragRes.json();
      const ragResults: ImageRagResult[] = ragData.results ?? [];
      console.log("[loading-page] image-rag response:", ragData);
      console.log("[loading-page] image-rag results count:", ragResults.length);

      setCurrentStep(3); // step 2 done → step 3 active

      /* ══════════════════════════════════════════
         STEP 3 — Top 3 추출 (추가 API 없음)
      ══════════════════════════════════════════ */
      const top3 = ragResults.slice(0, 3);

      /* 결과 저장 */
      sessionStorage.setItem(
        "recommendation_result",
        JSON.stringify({
          filteredGames,
          rankedGames,
          ragResults,
          top3,
        })
      );

      setCurrentStep(4); // step 3 done
      setAllDone(true);

    } catch (err: any) {
      console.error("[loading-page] Pipeline error:", err);
      setErrorMsg(err?.message ? err.message : JSON.stringify(err));
      fetchedRef.current = false; // 실패 시 재시도 가능하도록 해제
    }
  }

  return (
    <main className="loading-page">
      <div className="loading-card">
        <h1 className="title">
          <span className="title-accent">추천을 만들고 있어!</span>
        </h1>

        <ul className="loading-list">
          {steps.map((step, index) => (
            <li
              key={index}
              className={`loading-item ${
                index === currentStep ? "active" : ""
              } ${index < currentStep ? "done" : ""}`}
            >
              <span className="loading-dot" />
              <span>{step.icon}</span>
              <span>{step.text}</span>
            </li>
          ))}
        </ul>

        {errorMsg && (
          <p style={{ color: "#c0392b", marginTop: 20, textAlign: "center" }}>
            ⚠️ {errorMsg}
          </p>
        )}

        {allDone && (
          <button
            className="loading-final-btn"
            onClick={() => router.push("/select-game")}
          >
            이제 보여줄게!
          </button>
        )}
      </div>

      <button className="restart-btn" onClick={() => router.push("/")}>
        처음부터 다시하기
      </button>
    </main>
  );
}
