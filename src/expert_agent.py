"""
Social Media Expert Agent.
Reads both repos' code + saved analytics data, then answers a question via Gemini.
Output: docs/expert_response.json
"""
import os
import sys
import json
import re
import time
import base64
import datetime
import requests

QUESTION   = os.environ['QUESTION']
GEMINI_KEY = os.environ['GEMINI_API_KEY'].strip()
PAT        = os.environ.get('FIX_PAT', '')

GH      = 'https://api.github.com'
GEMINI  = 'https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent'

GH_HEADERS = {
    'Authorization':        f'Bearer {PAT}',
    'Accept':               'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
}

REPOS = {
    'friends': 'rg-incognito/shortgen',
    'himym':   'rg-incognito/shortgen-himym',
}

FILES = ['src/analyzer.py', 'src/main.py', 'src/captioner.py']


def fetch_file(repo: str, path: str) -> str:
    r = requests.get(f'{GH}/repos/{repo}/contents/{path}',
                     headers=GH_HEADERS, timeout=30)
    if not r.ok:
        return f'(could not fetch {path}: {r.status_code})'
    return base64.b64decode(r.json()['content']).decode('utf-8')


def call_gemini(prompt: str, retries: int = 3) -> dict:
    payload = {
        'contents':         [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.3},
    }
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(GEMINI, params={'key': GEMINI_KEY},
                              json=payload, timeout=120)
            r.raise_for_status()
            raw = r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
            raw = re.sub(r'\s*```$',          '', raw, flags=re.MULTILINE)
            return json.loads(raw)
        except Exception as e:
            print(f'  Gemini attempt {attempt} failed: {e}')
            if attempt < retries:
                time.sleep(20)
    raise RuntimeError('Gemini failed after all retries')


def _trim(text: str, chars: int = 4000) -> str:
    return text[:chars] + '\n...(truncated)' if len(text) > chars else text


def main():
    print(f'Question: {QUESTION}')

    # ── 1. Load saved analytics ───────────────────────────────────────────────
    print('[1/3] Loading analytics data...')
    analytics_path = 'docs/analytics_data.json'
    try:
        with open(analytics_path) as f:
            analytics = json.load(f)
        print(f'      Loaded analytics ({analytics.get("generated_at","?")})')
    except FileNotFoundError:
        analytics = {}
        print('      analytics_data.json not found — analytics context will be empty')

    def fmt_videos(videos: list) -> str:
        if not videos:
            return 'No data.'
        lines = []
        for v in videos[:15]:
            lines.append(
                f"  [{v.get('days_old',0)}d] {v.get('views',0):,} views | "
                f"{v.get('likes',0):,} likes | {v.get('comments',0):,} comments | "
                f"{v.get('duration_sec',0)}s | \"{v.get('title','')}\" | {v.get('url','')}"
            )
        return '\n'.join(lines)

    c1_videos   = analytics.get('channel1_videos', [])
    c2_videos   = analytics.get('channel2_videos', [])
    c1_analysis = analytics.get('channel1_analysis', {})
    c2_analysis = analytics.get('channel2_analysis', {})

    # ── 2. Fetch repo code ────────────────────────────────────────────────────
    print('[2/3] Fetching pipeline code from both repos...')
    repo_context = {}
    for channel, repo in REPOS.items():
        repo_context[channel] = {}
        for filepath in FILES:
            content = fetch_file(repo, filepath)
            repo_context[channel][filepath] = content
            print(f'      {channel}/{filepath} ({len(content):,} chars)')

    # ── 3. Build prompt and call Gemini ───────────────────────────────────────
    print('[3/3] Calling Gemini social media expert...')

    friends_summary = json.dumps(c1_analysis, indent=2)[:800] if c1_analysis else 'No AI analysis available.'
    himym_summary   = json.dumps(c2_analysis, indent=2)[:800] if c2_analysis else 'No AI analysis available.'

    prompt = f"""You are an elite YouTube Shorts social media strategist and data analyst. You have FULL access to both the performance metrics AND the actual automation code driving two clips channels.

QUESTION FROM CHANNEL OWNER:
{QUESTION}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRIENDS CLIPS CHANNEL — PERFORMANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{fmt_videos(c1_videos)}

AI Analysis Summary:
{friends_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HIMYM CLIPS CHANNEL — PERFORMANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{fmt_videos(c2_videos)}

AI Analysis Summary:
{himym_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRIENDS PIPELINE CODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
=== src/analyzer.py (Gemini prompt that picks clips + generates YouTube title/description) ===
{_trim(repo_context['friends'].get('src/analyzer.py', ''), 3500)}

=== src/main.py (MAX_RUNS, scheduling, upload logic) ===
{_trim(repo_context['friends'].get('src/main.py', ''), 1500)}

=== src/captioner.py (caption font, size, style, word highlighting) ===
{_trim(repo_context['friends'].get('src/captioner.py', ''), 1500)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HIMYM PIPELINE CODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
=== src/analyzer.py ===
{_trim(repo_context['himym'].get('src/analyzer.py', ''), 3500)}

=== src/main.py ===
{_trim(repo_context['himym'].get('src/main.py', ''), 1500)}

=== src/captioner.py ===
{_trim(repo_context['himym'].get('src/captioner.py', ''), 1500)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Answer the question with deep expertise. You can see the actual prompts, settings, and code — reference specific things you observe (e.g. "your _YT_PROMPT requires character-brand titles which limits curiosity gap" or "captioner.py uses font size 52 which is small for 9:16").

Return ONLY valid JSON:
{{
  "answer": "comprehensive answer — be specific, reference actual code/numbers, 3-6 paragraphs",
  "key_insights": ["specific insight 1 with evidence", "insight 2", "insight 3"],
  "specific_changes": [
    "File: src/analyzer.py — Change X to Y because Z",
    "File: src/captioner.py — Change X to Y because Z"
  ],
  "follow_up_questions": ["question the owner might want to ask next", "question 2"]
}}"""

    result = call_gemini(prompt)

    # ── Save response ─────────────────────────────────────────────────────────
    output = {
        'question':     QUESTION,
        'answer':       result.get('answer', ''),
        'key_insights': result.get('key_insights', []),
        'specific_changes': result.get('specific_changes', []),
        'follow_up_questions': result.get('follow_up_questions', []),
        'generated_at': datetime.datetime.utcnow().isoformat() + 'Z',
    }

    with open('docs/expert_response.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\nDone. Answer ({len(output["answer"])} chars) saved to docs/expert_response.json')


if __name__ == '__main__':
    main()
