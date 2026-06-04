"""
AI-powered code fixer using Claude Sonnet.
Reads source files from the target repo, asks Claude for surgical edits,
applies them as targeted str_replace operations, then opens a PR.
"""
import os
import sys
import json
import re
import ast
import time
import base64
import requests

CHANNEL      = os.environ['CHANNEL']        # 'friends' or 'himym'
ACTION       = os.environ['ACTION_ITEM']
WHY          = os.environ.get('WHY', '')
GEMINI_KEY   = os.environ['GEMINI_API_KEY'].strip()
PAT          = os.environ['FIX_PAT']

REPO_MAP = {
    'friends': 'rg-incognito/shortgen',
    'himym':   'rg-incognito/shortgen-himym',
}
TARGET = REPO_MAP.get(CHANNEL)
if not TARGET:
    print(f'Unknown channel: {CHANNEL}')
    sys.exit(1)

GH  = 'https://api.github.com'
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


# ── GitHub helpers ────────────────────────────────────────────────────────────

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
    if r.status_code not in (201, 422):
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


# ── Gemini ────────────────────────────────────────────────────────────────────

_GEMINI_URL = 'https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent'

def call_gemini(prompt: str, retries: int = 3) -> str:
    payload = {
        'contents':         [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.1},
    }
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(_GEMINI_URL, params={'key': GEMINI_KEY},
                              json=payload, timeout=120)
            r.raise_for_status()
            return r.json()['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            print(f'  Gemini attempt {attempt} failed: {e}')
            if attempt < retries:
                time.sleep(20)
    raise RuntimeError('Gemini failed after all retries')


# ── Python syntax check ───────────────────────────────────────────────────────

def _is_valid_python(src: str) -> bool:
    try:
        ast.parse(src)
        return True
    except SyntaxError as e:
        print(f'  Syntax error: {e}')
        return False


# ── Apply str_replace edits ───────────────────────────────────────────────────

def apply_edits(original: str, edits: list, filepath: str) -> str:
    result = original
    for i, edit in enumerate(edits):
        old = edit['old_string']
        new = edit['new_string']
        if old not in result:
            raise ValueError(
                f'Edit #{i+1} in {filepath}: old_string not found in file.\n'
                f'old_string was: {old[:120]!r}'
            )
        result = result.replace(old, new, 1)
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f'Target repo : {TARGET}')
    print(f'Channel     : {CHANNEL}')
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

    series = 'How I Met Your Mother' if CHANNEL == 'himym' else 'Friends'
    files_block = '\n\n'.join(
        f'### {p}\n```python\n{d["content"]}\n```' for p, d in file_data.items()
    )

    # ── 2. Claude generates surgical edits ───────────────────────────────────
    print('\n[2/4] Asking Claude to generate surgical fix...')

    prompt = f"""You are a senior Python engineer maintaining a YouTube Shorts automation pipeline for a {series} clips channel on GitHub.

## Task
Implement this specific action item by making MINIMAL, SURGICAL code changes:

**Action item:** {ACTION}

**Why it matters:** {WHY}

## Source files (read carefully before editing)

{files_block}

## Instructions

1. Identify EXACTLY which lines need to change to implement the action item
2. Make the smallest possible edit — change only what is necessary
3. Do NOT rewrite entire functions or files
4. Do NOT change unrelated code, variable names, or formatting
5. Ensure the logic is correct — think through side effects before editing
6. If the action involves a prompt string in analyzer.py, edit only that specific part of the string

Return ONLY a valid JSON object (no markdown, no explanation):
{{
  "branch_name": "fix/short-slug-under-40-chars",
  "pr_title": "fix: short description (under 60 chars)",
  "pr_body": "## What changed\\n- specific bullet describing exact change\\n\\n## Why\\n{WHY}\\n\\n## Expected outcome\\n...",
  "edits": [
    {{
      "file": "src/analyzer.py",
      "old_string": "exact verbatim text from the file to be replaced — must match 100%",
      "new_string": "the replacement text"
    }}
  ]
}}

CRITICAL: `old_string` must be the EXACT text from the file above, character for character including whitespace and indentation. If it doesn't match exactly, the edit will fail."""

    raw = call_gemini(prompt)
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r'\s*```$',          '', raw,          flags=re.MULTILINE)

    try:
        fix = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f'Claude returned invalid JSON: {e}')
        print(raw[:500])
        sys.exit(1)

    print(f'      Branch  : {fix["branch_name"]}')
    print(f'      PR title: {fix["pr_title"]}')
    print(f'      Edits   : {len(fix["edits"])} change(s) across {len({e["file"] for e in fix["edits"]})} file(s)')

    # ── 3. Apply edits locally + validate ────────────────────────────────────
    print('\n[3/4] Applying edits and validating...')
    patched: dict[str, str] = {}
    for edit in fix['edits']:
        path = edit['file']
        if path not in file_data:
            print(f'  SKIP: {path} was not in the files we read')
            continue
        original = file_data[path]['content']
        try:
            updated = apply_edits(
                patched.get(path, original),
                [edit],
                path,
            )
        except ValueError as e:
            print(f'  ERROR: {e}')
            sys.exit(1)

        if path.endswith('.py') and not _is_valid_python(updated):
            print(f'  ERROR: {path} has syntax errors after edit — aborting')
            sys.exit(1)

        patched[path] = updated
        print(f'      Patched {path}')

    if not patched:
        print('No files were patched — nothing to commit')
        sys.exit(1)

    # ── 4. Create branch, push files, open PR ────────────────────────────────
    print('\n[4/4] Creating branch and opening PR...')
    base_sha    = gh_get_default_sha(TARGET)
    branch_name = fix['branch_name']
    gh_create_branch(TARGET, branch_name, base_sha)

    for path, new_content in patched.items():
        sha = file_data[path]['sha']
        gh_update_file(TARGET, path, f'{fix["pr_title"]} [{path}]', new_content, sha, branch_name)

    pr_url = gh_create_pr(TARGET, fix['pr_title'], fix['pr_body'], branch_name)
    print(f'\nDone! PR: {pr_url}')


if __name__ == '__main__':
    main()
