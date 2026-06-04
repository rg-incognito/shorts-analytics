"""Main orchestrator: fetch data, run AI analysis, build HTML report."""
import os
import sys
import json
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fetch_analytics import get_channel_id, get_recent_videos
from ai_analyst import analyze_channels


# ── channel names for display ──────────────────────────────────────────────
CHANNEL1_NAME = 'Friends Clips'
CHANNEL2_NAME = 'HIMYM Clips'


def _health_color(health: str) -> str:
    return {'good': '#22c55e', 'warning': '#f59e0b', 'critical': '#ef4444'}.get(health, '#94a3b8')


def _trend_icon(trend: str) -> str:
    return {'growing': '↑', 'stable': '→', 'declining': '↓'}.get(trend, '?')


def _trend_color(trend: str) -> str:
    return {'growing': '#22c55e', 'stable': '#94a3b8', 'declining': '#ef4444'}.get(trend, '#94a3b8')


def _video_card(v: dict) -> str:
    bar_pct = min(100, v['views'] // 1000)
    return f"""
    <div class="video-card">
      <a href="{v['url']}" target="_blank" class="thumb-link">
        <img src="{v['thumbnail']}" alt="" class="thumb" loading="lazy">
        <span class="dur-badge">{v['duration_sec']}s</span>
      </a>
      <div class="card-body">
        <p class="card-title" title="{v['title']}">{v['title'][:72]}{'…' if len(v['title']) > 72 else ''}</p>
        <div class="stats-row">
          <span class="stat">👁 {v['views']:,}</span>
          <span class="stat">👍 {v['likes']:,}</span>
          <span class="stat">💬 {v['comments']:,}</span>
          <span class="stat age">{v['days_old']}d ago</span>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:{bar_pct}%"></div></div>
      </div>
    </div>"""


def _channel_section(ch_data: dict, videos: list) -> str:
    if not ch_data:
        return '<p class="muted">No AI analysis available.</p>'

    trend_html = f'<span style="color:{_trend_color(ch_data.get("trend","stable"))}">{_trend_icon(ch_data.get("trend","stable"))} {ch_data.get("trend","stable").title()}</span>'
    avg = ch_data.get('avg_views', 0)

    issues_html = ''.join(f'<li class="issue">{i}</li>' for i in ch_data.get('issues', []))
    wins_html   = ''.join(f'<li class="win">{w}</li>' for w in ch_data.get('wins', []))

    actions_html = ''
    for a in ch_data.get('top_actions', []):
        actions_html += f"""
        <div class="action-card">
          <div class="action-priority">#{a.get('priority','?')}</div>
          <div class="action-body">
            <p class="action-text">{a.get('action','')}</p>
            <p class="action-why">Why: {a.get('why','')}</p>
            <p class="action-impact">Impact: {a.get('expected_impact','')}</p>
          </div>
        </div>"""

    best = ch_data.get('best_video', {})
    worst = ch_data.get('worst_video', {})
    highlights = ''
    if best.get('title'):
        highlights += f'<div class="highlight best">🏆 Best: <a href="{best.get("url","#")}" target="_blank">{best["title"][:60]}</a> — {best.get("views",0):,} views</div>'
    if worst.get('title'):
        highlights += f'<div class="highlight worst">📉 Lowest: <a href="{worst.get("url","#")}" target="_blank">{worst["title"][:60]}</a> — {worst.get("views",0):,} views</div>'

    video_cards = ''.join(_video_card(v) for v in videos[:10])

    return f"""
    <div class="ch-meta">
      <span class="avg-badge">Avg {avg:,} views</span>
      {trend_html}
    </div>
    {highlights}
    <div class="two-col">
      <div>
        <h4 class="list-heading warn-head">Issues</h4>
        <ul class="insight-list">{issues_html}</ul>
      </div>
      <div>
        <h4 class="list-heading win-head">Wins</h4>
        <ul class="insight-list">{wins_html}</ul>
      </div>
    </div>
    <h4 class="list-heading">Top Actions</h4>
    <div class="actions-list">{actions_html}</div>
    <h4 class="list-heading">Recent Videos</h4>
    <div class="video-grid">{video_cards}</div>"""


def build_html(analysis: dict, c1_videos: list, c2_videos: list) -> str:
    now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    health  = analysis.get('overall_health', 'warning')
    hcolor  = _health_color(health)
    summary = analysis.get('summary', '')
    focus   = analysis.get('this_week_focus', '')

    channels = analysis.get('channels', {})
    c1 = channels.get('channel1', {})
    c2 = channels.get('channel2', {})

    cross = analysis.get('cross_channel_insights', [])
    cross_html = ''.join(f'<li>{i}</li>' for i in cross)

    c1_section = _channel_section(c1, c1_videos)
    c2_section = _channel_section(c2, c2_videos)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shorts Analytics Dashboard</title>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #6366f1;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.6; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .muted {{ color: var(--muted); }}
  header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; gap: 16px; }}
  header h1 {{ font-size: 18px; font-weight: 700; }}
  .badge {{ padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; color: #fff; }}
  .updated {{ margin-left: auto; color: var(--muted); font-size: 12px; }}
  main {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
  .summary-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
  .summary-card h2 {{ font-size: 14px; color: var(--muted); margin-bottom: 8px; text-transform: uppercase; letter-spacing: .05em; }}
  .summary-text {{ font-size: 15px; margin-bottom: 16px; }}
  .focus-box {{ background: #1a2744; border-left: 3px solid var(--accent); padding: 12px 16px; border-radius: 0 8px 8px 0; }}
  .focus-box strong {{ color: var(--accent); }}
  .channels-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
  @media (max-width: 900px) {{ .channels-grid {{ grid-template-columns: 1fr; }} }}
  .channel-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
  .channel-card h3 {{ font-size: 16px; font-weight: 700; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }}
  .ch-meta {{ display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }}
  .avg-badge {{ background: #1e3a5f; color: #93c5fd; padding: 4px 10px; border-radius: 8px; font-size: 13px; font-weight: 600; }}
  .highlight {{ padding: 8px 12px; border-radius: 8px; font-size: 13px; margin-bottom: 8px; }}
  .highlight.best {{ background: #14532d22; border: 1px solid #166534; }}
  .highlight.worst {{ background: #7f1d1d22; border: 1px solid #991b1b; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 16px 0; }}
  .list-heading {{ font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 16px 0 8px; }}
  .warn-head {{ color: #fbbf24; }}
  .win-head  {{ color: #34d399; }}
  .insight-list {{ list-style: none; padding: 0; }}
  .insight-list li {{ padding: 4px 0; font-size: 13px; padding-left: 16px; position: relative; }}
  .insight-list li::before {{ content: '•'; position: absolute; left: 0; }}
  .insight-list .issue::before {{ color: #f87171; }}
  .insight-list .win::before  {{ color: #34d399; }}
  .actions-list {{ display: flex; flex-direction: column; gap: 8px; }}
  .action-card {{ background: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 12px; display: flex; gap: 12px; }}
  .action-priority {{ background: var(--accent); color: #fff; font-weight: 700; font-size: 13px; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 2px; }}
  .action-text {{ font-size: 13px; font-weight: 600; margin-bottom: 4px; }}
  .action-why, .action-impact {{ font-size: 12px; color: var(--muted); }}
  .action-impact {{ color: #86efac; }}
  .video-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-top: 8px; }}
  .video-card {{ background: #0f172a; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
  .thumb-link {{ position: relative; display: block; }}
  .thumb {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }}
  .dur-badge {{ position: absolute; bottom: 4px; right: 4px; background: rgba(0,0,0,.8); color: #fff; font-size: 11px; padding: 1px 5px; border-radius: 4px; }}
  .card-body {{ padding: 8px; }}
  .card-title {{ font-size: 12px; line-height: 1.4; margin-bottom: 6px; color: var(--text); }}
  .stats-row {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .stat {{ font-size: 11px; color: var(--muted); }}
  .stat.age {{ margin-left: auto; }}
  .bar-track {{ background: var(--border); border-radius: 4px; height: 3px; margin-top: 6px; }}
  .bar-fill {{ background: var(--accent); border-radius: 4px; height: 3px; }}
  .cross-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
  .cross-card h3 {{ font-size: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 12px; }}
  .cross-card ul {{ list-style: none; padding: 0; }}
  .cross-card li {{ padding: 6px 0; padding-left: 20px; position: relative; border-bottom: 1px solid var(--border); font-size: 13px; }}
  .cross-card li::before {{ content: '⚡'; position: absolute; left: 0; }}
  footer {{ text-align: center; color: var(--muted); font-size: 12px; padding: 24px; border-top: 1px solid var(--border); margin-top: 24px; }}
</style>
</head>
<body>
<header>
  <h1>Shorts Analytics</h1>
  <span class="badge" style="background:{hcolor}">{health.upper()}</span>
  <span class="updated">Last updated: {now_str}</span>
</header>
<main>
  <div class="summary-card">
    <h2>Executive Summary</h2>
    <p class="summary-text">{summary}</p>
    <div class="focus-box"><strong>This Week's Focus:</strong> {focus}</div>
  </div>

  <div class="channels-grid">
    <div class="channel-card">
      <h3>{CHANNEL1_NAME}</h3>
      {c1_section}
    </div>
    <div class="channel-card">
      <h3>{CHANNEL2_NAME}</h3>
      {c2_section}
    </div>
  </div>

  <div class="cross-card">
    <h3>Cross-Channel Insights</h3>
    <ul>{cross_html}</ul>
  </div>
</main>
<footer>Auto-refreshed every 5 hours via GitHub Actions + cron-job.org</footer>
</body>
</html>"""


def main():
    friends_token = os.environ['FRIENDS_YT_TOKEN_JSON']
    himym_token   = os.environ['HIMYM_YT_TOKEN_JSON']
    gemini_key    = os.environ['GEMINI_API_KEY']

    print("[1/3] Fetching Friends channel data...")
    c1_id     = get_channel_id(friends_token)
    c1_videos = get_recent_videos(friends_token, c1_id, max_results=20)
    print(f"      {len(c1_videos)} videos fetched")

    print("[2/3] Fetching HIMYM channel data...")
    c2_id     = get_channel_id(himym_token)
    c2_videos = get_recent_videos(himym_token, c2_id, max_results=20)
    print(f"      {len(c2_videos)} videos fetched")

    print("[3/3] Running AI analysis...")
    analysis = analyze_channels(
        CHANNEL1_NAME, c1_videos,
        CHANNEL2_NAME, c2_videos,
        gemini_key,
    )
    print(f"      Health: {analysis.get('overall_health')}")
    print(f"      Focus: {analysis.get('this_week_focus','')[:80]}")

    html = build_html(analysis, c1_videos, c2_videos)

    out_path = Path(__file__).parent.parent / 'docs' / 'index.html'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding='utf-8')
    print(f"\nReport written to {out_path}")


if __name__ == '__main__':
    main()
