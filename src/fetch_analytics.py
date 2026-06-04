"""Fetch video stats from YouTube Data API v3 for both channels."""
import os
import json
import datetime
import requests

_YT_API = 'https://www.googleapis.com/youtube/v3'


def _get_headers(token_json_str: str) -> dict:
    token = json.loads(token_json_str)
    return {'Authorization': f"Bearer {token['token']}"}


def _refresh_token(token_json_str: str) -> str:
    """Refresh expired access token using refresh_token."""
    t = json.loads(token_json_str)
    resp = requests.post(
        t.get('token_uri', 'https://oauth2.googleapis.com/token'),
        data={
            'client_id':     t['client_id'],
            'client_secret': t['client_secret'],
            'refresh_token': t['refresh_token'],
            'grant_type':    'refresh_token',
        },
        timeout=30,
    )
    resp.raise_for_status()
    t['token'] = resp.json()['access_token']
    return json.dumps(t)


def _api_get(url, params, token_json_str):
    headers = _get_headers(token_json_str)
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if resp.status_code == 401:
        token_json_str = _refresh_token(token_json_str)
        headers = _get_headers(token_json_str)
        resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_channel_id(token_json_str: str) -> str:
    data = _api_get(
        f'{_YT_API}/channels',
        {'part': 'id', 'mine': 'true'},
        token_json_str,
    )
    return data['items'][0]['id']


def get_recent_videos(token_json_str: str, channel_id: str, max_results: int = 20) -> list:
    """Return list of video dicts with stats for the most recent uploads."""
    # Get uploads playlist
    data = _api_get(
        f'{_YT_API}/channels',
        {'part': 'contentDetails', 'id': channel_id},
        token_json_str,
    )
    uploads_playlist = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    # Get recent video IDs
    pl_data = _api_get(
        f'{_YT_API}/playlistItems',
        {
            'part':       'contentDetails,snippet',
            'playlistId': uploads_playlist,
            'maxResults': max_results,
        },
        token_json_str,
    )
    items = pl_data.get('items', [])
    video_ids = [i['contentDetails']['videoId'] for i in items]
    publish_map = {
        i['contentDetails']['videoId']: i['snippet']['publishedAt']
        for i in items
    }

    if not video_ids:
        return []

    # Batch stats
    stats_data = _api_get(
        f'{_YT_API}/videos',
        {
            'part': 'statistics,snippet,contentDetails',
            'id':   ','.join(video_ids),
        },
        token_json_str,
    )

    videos = []
    for v in stats_data.get('items', []):
        vid_id  = v['id']
        snippet = v['snippet']
        stats   = v.get('statistics', {})
        cd      = v.get('contentDetails', {})

        # Parse ISO 8601 duration to seconds
        dur_str = cd.get('duration', 'PT0S')
        duration_sec = _parse_duration(dur_str)

        published_at = publish_map.get(vid_id, snippet.get('publishedAt', ''))
        days_old = _days_since(published_at)

        videos.append({
            'video_id':      vid_id,
            'title':         snippet.get('title', ''),
            'published_at':  published_at,
            'days_old':      days_old,
            'duration_sec':  duration_sec,
            'views':         int(stats.get('viewCount', 0)),
            'likes':         int(stats.get('likeCount', 0)),
            'comments':      int(stats.get('commentCount', 0)),
            'thumbnail':     snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
            'url':           f'https://youtu.be/{vid_id}',
        })

    # Sort newest first
    videos.sort(key=lambda x: x['published_at'], reverse=True)
    return videos


def _parse_duration(iso: str) -> int:
    import re
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s


def _days_since(iso_date: str) -> int:
    if not iso_date:
        return 0
    try:
        dt = datetime.datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        now = datetime.datetime.now(datetime.timezone.utc)
        return (now - dt).days
    except Exception:
        return 0
