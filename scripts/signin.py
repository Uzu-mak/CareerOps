"""Sign in to a job site once so CareerOps can apply there with your session.

Run on your own computer (not inside Docker):

    signin.bat https://www.metacareers.com/login
    python scripts/signin.py https://www.metacareers.com/login [--careerops http://localhost:8001] [--token API_TOKEN]

A normal Chrome window opens. Sign in yourself (including any emailed or texted
code), then come back to this window and press Enter. The site's cookies are sent
to CareerOps and reused by the browser agent for that site. Your password is
never seen or stored by CareerOps. Delete a session any time on Sources & automation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser(description='Save a job-site sign-in for CareerOps')
    ap.add_argument('url', help='Sign-in page or any page of the site, in quotes')
    ap.add_argument('--careerops', default=os.environ.get('CAREEROPS_URL', 'http://localhost:8001'), help='CareerOps address')
    ap.add_argument('--token', default=os.environ.get('CAREEROPS_API_TOKEN', ''), help='API_TOKEN for a hosted CareerOps')
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Playwright is not installed. Run:  py -m pip install --user playwright   then try again.')
        return 1

    with sync_playwright() as p:
        browser = None
        for channel in ('chrome', 'msedge', None):          # use the browser already on this PC
            try:
                browser = p.chromium.launch(headless=False, **({'channel': channel} if channel else {}))
                break
            except Exception:
                continue
        if browser is None:
            print('No browser found. Run:  py -m playwright install chromium   then try again.')
            return 1
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = context.new_page()
        page.goto(args.url)
        print()
        print('  1. Sign in in the browser window that just opened.')
        print('  2. When you can see you are signed in, come back here and press Enter.')
        input('  Press Enter when done... ')
        state = context.storage_state()
        final_url = page.url
        browser.close()

    body = json.dumps({'url': final_url or args.url, 'storage_state': state}).encode()
    req = urllib.request.Request(args.careerops.rstrip('/') + '/api/portal-sessions', data=body, method='POST',
                                 headers={'Content-Type': 'application/json', **({'Authorization': f'Bearer {args.token}'} if args.token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(f'CareerOps refused the session ({exc.code}): {exc.read().decode(errors="replace")[:300]}')
        return 1
    except urllib.error.URLError as exc:
        print(f'Could not reach CareerOps at {args.careerops}: {exc.reason}. Is it running?')
        return 1
    print(f'\n  Saved sign-in for {out["site"]} ({out["cookies"]} cookies). CareerOps will use it when applying there.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
