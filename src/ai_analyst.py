"""Gemini social-media specialist analysis for both channels."""
import json
import re
import time
import requests

_GEMINI_URL = 'https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent'

_SYSTEM_PROMPT = """You are an elite YouTube Shorts growth specialist with 10+ years managing viral short-form content channels. You have deep expertise in:
- Hook engineering (first 0.5 seconds determines 80% of retention)
- Shorts algorithm: watch time %, swipe-away rate, re-watch loops
- Title psychology: curiosity gap, narrative vs. character-brand formats
- Thumbnail click psychology
- Caption style impact on retention
- Posting time optimization
- Community engagement tactics

You are reviewing performance data for a How I Met Your Mother / Friends clips channel and giving SPECIFIC, ACTIONABLE feedback — not generic advice.

IMPORTANT: Be brutally honest. If something is underperforming, say exactly why and what to change."""

_ANALYSIS_PROMPT = """Here is the recent performance data for TWO YouTube Shorts channels:

=== CHANNEL 1: {channel1_name} ===
{channel1_data}

=== CHANNEL 2: {channel2_name} ===
{channel2_data}

Analyze this data and return ONLY a valid JSON object with this exact structure:
{{
  "overall_health": "good|warning|critical",
  "summary": "2-3 sentence executive summary of both channels combined",
  "channels": {{
    "channel1": {{
      "name": "{channel1_name}",
      "avg_views": <number>,
      "best_video": {{"title": "...", "views": <n>, "url": "..."}},
      "worst_video": {{"title": "...", "views": <n>, "url": "..."}},
      "trend": "growing|stable|declining",
      "issues": ["specific issue 1", "specific issue 2"],
      "wins": ["specific win 1"],
      "top_actions": [
        {{"priority": 1, "action": "exact thing to change", "why": "data-backed reason", "expected_impact": "what metric improves and by how much"}}
      ]
    }},
    "channel2": {{
      "name": "{channel2_name}",
      "avg_views": <number>,
      "best_video": {{"title": "...", "views": <n>, "url": "..."}},
      "worst_video": {{"title": "...", "views": <n>, "url": "..."}},
      "trend": "growing|stable|declining",
      "issues": ["specific issue 1", "specific issue 2"],
      "wins": ["specific win 1"],
      "top_actions": [
        {{"priority": 1, "action": "exact thing to change", "why": "data-backed reason", "expected_impact": "what metric improves and by how much"}}
      ]
    }}
  }},
  "cross_channel_insights": [
    "insight comparing both channels",
    "which show performs better on which metric and why"
  ],
  "this_week_focus": "The ONE most important thing to fix this week across both channels"
}}"""


def _format_channel_data(videos: list) -> str:
    if not videos:
        return "No data available."
    lines = []
    for v in videos[:15]:
        age = f"{v['days_old']}d old" if v['days_old'] > 0 else "today"
        dur = f"{v['duration_sec']}s"
        lines.append(
            f"- [{age}] {v['views']:,} views | {v['likes']:,} likes | {v['comments']:,} comments | {dur} | \"{v['title']}\" | {v['url']}"
        )
    return '\n'.join(lines)


def analyze_channels(channel1_name: str, channel1_videos: list,
                     channel2_name: str, channel2_videos: list,
                     gemini_api_key: str, retries: int = 3) -> dict:
    c1_data = _format_channel_data(channel1_videos)
    c2_data = _format_channel_data(channel2_videos)

    prompt = _SYSTEM_PROMPT + '\n\n' + _ANALYSIS_PROMPT.format(
        channel1_name=channel1_name,
        channel1_data=c1_data,
        channel2_name=channel2_name,
        channel2_data=c2_data,
    )

    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.3},
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                _GEMINI_URL,
                params={'key': gemini_api_key.strip()},
                json=payload,
                timeout=90,
            )
            resp.raise_for_status()
            raw = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
            raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
            return json.loads(raw)
        except Exception as e:
            print(f"  AI analysis attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(20)

    return {
        'overall_health': 'warning',
        'summary': 'AI analysis unavailable — showing raw data only.',
        'channels': {},
        'cross_channel_insights': [],
        'this_week_focus': 'Check API keys and retry.',
    }
