"""AI insights generation using the Geotab GenAI Gateway (OpenAI-compatible)."""
from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a senior fleet analytics consultant writing concise data-driven insights "
    "for a fleet management report. Be specific, cite numbers, and be actionable. "
    "When mentioning costs, use the currency code provided (e.g., MYR, IDR, USD) instead of symbols like $. "
    "Maximum 2–3 sentences per insight. Reply only with the insight text, no preamble."
)

SLIDE_INSTRUCTIONS: dict[str, str] = {
    "portfolio": "Write a 2-3 sentence insight for the Customer Portfolio slide. Mention the number of customer groups, total vehicles, and any unassigned vehicles.",
    "days_driven": "Write a 2-3 sentence insight for the Days Driven slide. Mention the Q1 threshold and how many vehicles are under-deployed.",
    "distance": "Write a 2-3 sentence insight for the Distance Travelled slide. Mention Q1/Q3 thresholds and highlight outliers.",
    "drive_hours": "Write a 2-3 sentence insight for the Driving Duration slide. Mention Q1/Q3 and hours for high/low performers.",
    "utilization_trend": "Write a 2-3 sentence insight for the Monthly Utilization Trend slide. Describe the trend direction and notable months.",
    "utilization_donut": "Write a 2-3 sentence insight for the Utilization Distribution donut chart. Highlight under and over-utilized proportions.",
    "utilization_table": "Write a 2-3 sentence insight for the Utilization by Vehicle table. Highlight the spread and identify key outliers.",
    "idling": "Write a 2-3 sentence insight for the Idling Duration slide. Mention total idle hours, estimated cost (use the currency code provided, not $ symbol), and trend.",
    "idling_top15": "Write a 2-3 sentence insight for the Top 15 Idling Vehicles slide. Identify key culprits and the business case for coaching.",
    "safety_donut": "Write a 2-3 sentence insight for the Safety Risk Overview donut. Mention high/medium risk counts and urgency.",
    "safety_events": "Write a 2-3 sentence insight for the Safety Events vbar. Identify the top violation type and its share of total events.",
    "max_speeding": "Write a 2-3 sentence insight for the Max Speeding slide. Mention the top recorded speed, how many vehicles exceeded dangerous thresholds, and the importance of speed management.",
    "safety_bottom15": "Write a 2-3 sentence insight for the Bottom 15 Safety Scores slide. Mention the threshold and coaching priority.",
    "battery": "Write a 2-3 sentence insight for the Battery Health slide. Mention fault event count and vehicles affected.",
    "battery_customers": "Write a 2-3 sentence insight for the Battery by Customer slide. Mention affected accounts.",
    "faults": "Write a 2-3 sentence insight for the Fault Codes slide. Mention top DTC codes and maintenance implications.",
    "risk": "Write a 2-3 sentence insight for the At-Risk Vehicles slide. Mention critical/high vehicles and the 5-factor matrix.",
    "risk_customers": "Write a 2-3 sentence insight for the At-Risk by Customer slide. Mention which accounts need priority follow-up.",
}


def _build_context(fleet_summary: dict) -> str:
    """Build a compact fleet summary string for the LLM prompt."""
    lines = ["Fleet Summary:"]
    for k, v in fleet_summary.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


async def _call_llm(
    client: AsyncOpenAI,
    model: str,
    slide_key: str,
    context: str,
    language: str,
) -> str:
    lang_suffix = " Respond in Bahasa Malaysia." if language == "ms" else ""
    instruction = SLIDE_INSTRUCTIONS.get(slide_key, f"Write a 2-3 sentence insight for the {slide_key} slide.")
    user_msg = f"{context}\n\n{instruction}{lang_suffix}"

    try:
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=settings.GENAI_MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("AI insight call failed for slide '%s': %s", slide_key, exc)
        return ""  # caller falls back to template string


async def _call_recommendations(
    client: AsyncOpenAI,
    model: str,
    context: str,
    language: str,
    n_recs: int = 8,
) -> list[str]:
    lang_suffix = " Respond in Bahasa Malaysia." if language == "ms" else ""
    user_msg = (
        f"{context}\n\n"
        f"Based on the fleet data above, write exactly {n_recs} actionable strategic recommendations "
        f"for the fleet manager. Each recommendation must:\n"
        "- Start with a bold title (e.g. 'Dormant Vehicles:')\n"
        "- Be 2-4 sentences\n"
        "- Reference specific numbers from the data\n"
        "- Be separated by a blank line\n"
        f"Number them 1-{n_recs}. No preamble.{lang_suffix}"
    )

    try:
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=settings.GENAI_RECS_MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        content = resp.choices[0].message.content.strip()
        # Split numbered list into individual recommendations
        import re
        parts = re.split(r'\n\d+\.\s+', "\n" + content)
        recs = [p.strip() for p in parts if p.strip()]
        return recs[:n_recs] if recs else [content]
    except Exception as exc:
        logger.warning("AI recommendations call failed: %s", exc)
        return []


async def generate_all_insights(
    fleet_summary: dict,
    slide_keys: list[str],
    language: str,
) -> tuple[dict[str, str], list[str]]:
    """
    Generate AI insights for all requested slides in parallel.

    Parameters
    ----------
    fleet_summary : dict of key metrics for the LLM context
    slide_keys    : list of slide_key strings to generate insights for
    language      : "en" or "ms"

    Returns
    -------
    (insights_dict, recommendations_list)
    insights_dict: {slide_key: insight_text}
    """
    if not settings.GENAI_API_KEY:
        logger.warning("GENAI_API_KEY not set — skipping AI insights")
        return {}, []

    client = AsyncOpenAI(
        api_key=settings.GENAI_API_KEY,
        base_url=settings.GENAI_GATEWAY_URL,
    )
    model = settings.GENAI_MODEL
    context = _build_context(fleet_summary)

    # Build coroutines for all per-slide calls
    tasks = {
        key: _call_llm(client, model, key, context, language)
        for key in slide_keys
        if key in SLIDE_INSTRUCTIONS
    }

    # Run slide insights in parallel
    if tasks:
        results_list = await asyncio.gather(*tasks.values())
        insights = dict(zip(tasks.keys(), results_list))
    else:
        insights = {}

    # Recommendations (sequential, after insights)
    recs = await _call_recommendations(client, model, context, language)

    return insights, recs
