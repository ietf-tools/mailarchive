#!/usr/bin/env python3
"""
Compare message detail responses between the Cloudflare worker and the Django app.

Randomly samples messages from the database, fetches each from both the worker
(port 8787) and the Django app (port 8000), and compares the full HTML responses.

Usage:
  python3 worker-checker.py [--max-pk N] [--count N] [--worker-url URL] [--app-url URL]
"""

# Standalone boilerplate -------------------------------------------------------
from django_setup import do_setup
do_setup()
# ------------------------------------------------------------------------------

import argparse
import difflib
import random
import re
import sys
import time
import urllib.error
import urllib.request

from mlarchive.archive.models import Message

# Normalize versioned static.ietf.org paths across app versions.
# Matches https://static.ietf.org/mailarchive/<version>/ and replaces the
# version segment with VERSION so comparisons are version-agnostic.
_RE_STATIC_IETF_VERSION = re.compile(
    r'(https://static\.ietf\.org/mailarchive/)[^/\s"\'<>]+/'
)

# Normalize the version string that appears only in the footer line, which
# contains the "Report a Bug" anchor as a reliable discriminator.
_RE_FOOTER_VERSION = re.compile(r'\bv\d+[\d.\w-]*\b')

# Cloudflare bot-challenge scripts injected in production responses vary per
# request (embedded nonces/tokens).  Drop any line that contains the challenge
# platform URL so the two responses compare equal when one has the script and
# the other doesn't, or when both have it with different token values.
_CF_CHALLENGE_MARKER = '/cdn-cgi/challenge-platform/'

# Cloudflare Automatic HTTPS Rewrites upgrades href="http://..." to
# href="https://..." in production responses but leaves display text unchanged.
# Normalize all href values to https so both sides compare equal.
_RE_HTTP_HREF = re.compile(r'\bhref="http://')


def fetch(url, timeout=15):
    """Return (status, headers_dict, body_text) for url."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode('utf-8', errors='replace')
    except Exception as exc:
        return None, {}, str(exc)


def print_response(label, url, status, headers, body):
    """Print full request/response details for debugging."""
    print(f'  --- {label} ---')
    print(f'  URL:    {url}')
    print(f'  Status: {status}')
    for k, v in sorted(headers.items()):
        print(f'  {k}: {v}')
    print(f'  Body ({len(body)} chars):')
    print(body)
    print()


def normalize(html):
    """Normalize whitespace and version-specific content for stable comparison."""
    lines = []
    for line in html.splitlines():
        line = line.strip()
        if not line:
            continue
        # Drop Cloudflare bot-challenge script lines (tokens vary per request)
        if _CF_CHALLENGE_MARKER in line:
            continue
        # Normalize href http→https (Cloudflare Automatic HTTPS Rewrites)
        line = _RE_HTTP_HREF.sub('href="https://', line)
        # Replace version segment in static.ietf.org/mailarchive/<version>/ URLs
        line = _RE_STATIC_IETF_VERSION.sub(r'\1VERSION/', line)
        # Replace app version string in the footer line only
        if 'Report a Bug' in line:
            line = _RE_FOOTER_VERSION.sub('vVERSION', line)
        lines.append(line)
    return lines


def check_message(msg, worker_base, app_base, verbose=False, show_worker_response=False):
    """
    Fetch the message from both endpoints and compare the full HTML.

    Returns (status, info_dict) where status is 'pass', 'fail', or 'skip'.
    """
    hashcode_url = msg.hashcode.rstrip('=')
    path = f'/arch/msg/{msg.email_list.name}/{hashcode_url}/'

    worker_url = f'{worker_base}{path}'
    app_url = f'{app_base}{path}'

    if verbose:
        print(f'  Fetching worker: {worker_url}')
        print(f'  Fetching app:    {app_url}')

    w_status, w_headers, w_html = fetch(worker_url)
    a_status, a_headers, a_html = fetch(app_url)

    if show_worker_response:
        print_response('worker', worker_url, w_status, w_headers, w_html)

    info = {
        'pk': msg.pk,
        'list': msg.email_list.name,
        'hashcode': hashcode_url,
        'path': path,
        'worker_status': w_status,
        'app_status': a_status,
        'served_by': w_headers.get('X-Served-By', ''),
        'worker_action': w_headers.get('X-Worker-Action', ''),
        'issues': [],
    }

    if w_status is None:
        info['issues'].append(f'worker connection error: {w_html}')
        return 'fail', info
    if a_status is None:
        info['issues'].append(f'app connection error: {a_html}')
        return 'fail', info

    if w_status != 200:
        info['issues'].append(f'worker returned HTTP {w_status}')
    if a_status != 200:
        info['issues'].append(f'app returned HTTP {a_status}')

    if info['issues']:
        return 'fail', info

    w_lines = normalize(w_html)
    a_lines = normalize(a_html)

    if w_lines == a_lines:
        return 'pass', info

    # Responses differ — generate a unified diff for reporting
    diff = list(difflib.unified_diff(
        a_lines, w_lines,
        fromfile='app',
        tofile='worker',
        lineterm='',
        n=2,
    ))
    info['diff'] = diff
    info['issues'].append(f'HTML differs ({len(diff)} diff lines)')
    return 'fail', info


def main():
    parser = argparse.ArgumentParser(
        description='Compare Cloudflare worker and Django app message detail responses'
    )
    parser.add_argument('--max-pk', type=int, metavar='N',
                        help='only consider messages with pk <= N')
    parser.add_argument('--count', type=int, default=10, metavar='N',
                        help='number of messages to sample (default: 10)')
    parser.add_argument('--worker-url', default='http://localhost:8787',
                        help='worker base URL (default: http://localhost:8787)')
    parser.add_argument('--app-url', default='http://localhost:8000',
                        help='app base URL (default: http://localhost:8000)')
    parser.add_argument('--diff', action='store_true',
                        help='print unified diff for failing messages')
    parser.add_argument('--verbose', action='store_true',
                        help='print the full URLs being fetched for each message')
    parser.add_argument('--show-worker-response', action='store_true',
                        help='print the complete worker HTTP response (status, headers, body)')
    parser.add_argument('--rate', type=float, default=30, metavar='N',
                        help='max requests per minute (default: 30)')
    args = parser.parse_args()

    qs = (Message.objects
          .filter(email_list__private=False, spam_score__lte=0)
          .select_related('email_list'))
    if args.max_pk:
        qs = qs.filter(pk__lte=args.max_pk)

    pks = list(qs.values_list('pk', flat=True))
    if not pks:
        print('No eligible messages found.')
        sys.exit(1)

    sample = random.sample(pks, min(args.count, len(pks)))
    messages = {m.pk: m for m in qs.filter(pk__in=sample)}

    passed = failed = 0
    delay = 60.0 / args.rate

    for pk in sample:
        msg = messages[pk]
        status, info = check_message(
            msg, args.worker_url, args.app_url,
            verbose=args.verbose,
            show_worker_response=args.show_worker_response,
        )

        served_tag = f'[{info["served_by"]}]' if info['served_by'] else f'[{info["worker_action"]}]'
        prefix = f"pk={info['pk']:>8}  {info['path']}  {served_tag}"

        if status == 'pass':
            passed += 1
            print(f'PASS  {prefix}')
        else:
            failed += 1
            print(f'FAIL  {prefix}')
            for issue in info['issues']:
                print(f'      {issue}')
            if args.diff and 'diff' in info:
                for line in info['diff'][:80]:
                    print(f'      {line}')
                if len(info['diff']) > 80:
                    print(f'      ... ({len(info["diff"]) - 80} more diff lines)')
        time.sleep(delay)

    total = passed + failed
    print(f'\n{total} checked — {passed} passed, {failed} failed')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
