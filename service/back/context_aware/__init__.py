# Phase 2: Context-aware — 지금 내가 어떤 상태인가 (요즘 어떤 게임을 하고 싶은가)
#
# 유저 컨텍스트 모듈:
#   (1) situational      — 상황/시간 (available_time, 요일/시간대)
#   (2) sentiment        — 심리/감성 (LLM 추출, mood_tag)
#   (4) play_style       — 플레이 스타일 (focus_score, difficulty_pref)
#   (5) behavior_activity — 최근 행동/활성도 (activity_state, anchor appids)
#
# 게임 컨텍스트 모듈:
#   (6) quality_trust    — 완성도/신뢰도
#   (7) live             — 라이브 상태 (업데이트/이벤트)
#   (8) discount         — 할인 트리거
#
# 조립기:
#   context_bundle       — 유저 + 게임 컨텍스트를 하나의 ContextBundle로 통합
