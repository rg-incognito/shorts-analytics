"""
AI-powered code fixer.
Reads source files from the target repo, calls Gemini to generate a fix,
then opens a PR with the changes.
"""
import os
import sys
import json
import re
import time
import base64
import requests

CHANNEL    = os.environ['CHANNEL']        # 'friends' or 'himym'
ACTION     = os.environ['ACTION_ITEM']
WHY        = os.environ.get('WHY', '')
GEMINI_KEY = os.environ['GEMINI_API_KEY'].strip()
PAT        = os.environ['FIX_PAT']

REPO_MAP = {
    'friends': 'rg-incognito/shortgen',
    'himym':   'rg-incognito/shortgen-himym',
}
TARGET = REPO_MAP.get(CHANNEL)
if not TARGET:
    print(f'Unknown channel: {CHANNEL}')
    sys.exit(1)

GH  = 'https://api.github.com'
GEM = 'https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent'

GH_HEADERS = {
    'Authorization':        f'Bearer {PAT}',
    'Accept':               'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
}

FILES_TO_READ = [
    'src/analyzer.py',
    'src/main.py',
    'src/clipper.py',
    'src/captioner.py',
    'src/reframer.py',
]


def gh_get_file(repo, path):
    r = requests.get(f'{GH}/repos/{repo}/contents/{path}', headers=GH_HEADERS, timeout=30)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    d = r.json()
    return base64.b64decode(d['content']).decode('utf-8'), d['sha']


def gh_get_default_sha(repo, branch='master'):
    r = requests.get(f'{GH}/repos/{repo}/git/ref/heads/{branch}', headers=GH_HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()['object']['sha']


def gh_create_branch(repo, branch, sha):
    r = requests.post(f'{GH}/repos/{repo}/git/refs', headers=GH_HEADERS,
                      json={'ref': f'refs/heads/{branch}', 'sha': sha}, timeout=30)
    if r.status_code not in (201, 422):  # 422 = branch already exists
        r.raise_for_status()


def gh_update_file(repo, path, message, content, sha, branch):
    body = {
        'message': message,
        'content': base64.b64encode(content.encode('utf-8')).decode(),
        'branch':  branch,
    }
    if sha:
        body['sha'] = sha
    r = requests.put(f'{GH}/repos/{repo}/contents/{path}', headers=GH_HEADERS,
                     json=body, timeout=60)
    r.raise_for_status()


def gh_create_pr(repo, title, body, head, base='master'):
    r = requests.post(f'{GH}/repos/{repo}/pulls', headers=GH_HEADERS,
                      json={'title': title, 'body': body, 'head': head, 'base': base},
                      timeout=30)
    r.raise_for_status()
    return r.json()['html_url']


def call_gemini(prompt, retries=3):
    payload = {
        'contents':        [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.2},
    }
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(GEM, params={'key': GEMINI_KEY}, json=payload, timeout=120)
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


def main():
    print(f'Target repo : {TARGET}')
    print(f'Action      : {ACTION}')
    print(f'Why         : {WHY}')

    # ── 1. Read source files ──────────────────────────────────────────────────
    print('\n[1/4] Reading source files...')
    file_data = {}
    for path in FILES_TO_READ:
        content, sha = gh_get_file(TARGET, path)
        if content is not None:
            file_data[path] = {'content': content, 'sha': sha}
            print(f'      {path} ({len(content):,} chars)')
        else:
            print(f'      {path} — not found, skipping')

    # ── 2. Gemini generates fix ───────────────────────────────────────────────
    print('\n[2/4] Asking Gemini to generate fix...')
    series = 'How I Met Your Mother' if CHANNEL == 'himym' else 'Friends'

    files_block = '\n\n'.join(
        f'=== {p} ===\n{d["content"]}' for p, d in file_data.items()
    )

    prompt = f"""You are an expert Python developer maintaining a YouTube Shorts automation pipeline for a {series} clips channel.

ACTION ITEM TO IMPLEMENT:
{ACTION}

WHY IT MATTERS:
{WHY}

CURRENT SOURCE FILES:
{files_block}

Your job: make the minimal, targeted code change that implements the action item.
- Only modify files that actually need to change
- Do NOT add comments about what you changed
- Keep all existing logic intact — just implement the specific improvement
- If the action involves the Gemini prompt (e.g. changing title format, adding storyline types, adjusting clip lengths), modify _PROMPT or _YT_PROMPT in analyzer.py
- If the action involves video processing (captions, font, layout), modify captioner.py or reframer.py

Return ONLY valid JSON with no markdown:
{{
  "branch_name": "fix/short-kebab-slug",
  "pr_title": "fix: short description (under 60 chars)",
  "pr_body": "## What changed\\n- specific bullet\\n\\n## Why\\n{WHY}\\n\\n## Expected impact\\n...",
  "changes": [
    {{
      "file": "src/analyzer.py",
      "new_content": "...complete new file content..."
    }}
  ]
}}"""

    fix = call_gemini(prompt)
    print(f'      Branch  : {fix["branch_name"]}')
    print(f'      PR title: {fix["pr_title"]}')
    print(f'      Files   : {[c["file"] for c in fix["changes"]]}')

    # ── 3. Create branch + apply changes ─────────────────────────────────────
    print('\n[3/4] Creating branch and applying changes...')
    base_sha    = gh_get_default_sha(TARGET)
    branch_name = fix['branch_name']
    gh_create_branch(TARGET, branch_name, base_sha)

    for change in fix['changes']:
        path  = change['file']
        old   = file_data.get(path, {})
        sha   = old.get('sha')
        msg   = f'{fix["pr_title"]} — {path}'
        gh_update_file(TARGET, path, msg, change['new_content'], sha, branch_name)
        print(f'      Updated {path}')

    # ── 4. Open PR ────────────────────────────────────────────────────────────
    print('\n[4/4] Opening pull request...')
    pr_url = gh_create_pr(TARGET, fix['pr_title'], fix['pr_body'], branch_name)
    print(f'\nDone! PR: {pr_url}')


if __name__ == '__main__':
    main()
