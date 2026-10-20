"""Fill an application in your own browser and submit it yourself.

For sites that refuse automated submissions (a hidden bot check): CareerOps fills
the form in a normal Chrome window on your computer, then you check it and click
Submit. Run on your own computer, not inside Docker:

    finish.bat 433
    python scripts/finish.py 433 [--careerops http://localhost:8001] [--token API_TOKEN]

433 is the job number in the CareerOps address bar (localhost:8001/jobs/433).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # the CareerOps folder


def call(base: str, token: str, path: str, method: str = 'GET'):
    req = urllib.request.Request(base.rstrip('/') + path, method=method, data=b'' if method == 'POST' else None,
                                 headers={**({'Authorization': f'Bearer {token}'} if token else {})})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read() or b'{}')


def main() -> int:
    ap = argparse.ArgumentParser(description='Fill a CareerOps application in your own browser')
    ap.add_argument('job', type=int, help='Job number from the CareerOps address bar')
    ap.add_argument('--careerops', default=os.environ.get('CAREEROPS_URL', 'http://localhost:8001'))
    ap.add_argument('--token', default=os.environ.get('CAREEROPS_API_TOKEN', ''))
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Playwright is not installed. Run:  py -m pip install --user playwright   then try again.')
        return 1
    from careerops.agents.apply_plan import build_facts
    from careerops.agents.browser import _settle, application_entry_url, prefill

    print('  Getting your answers and documents from CareerOps (first time can take a minute)...')
    try:
        kit = call(args.careerops, args.token, f'/api/jobs/{args.job}/fill-kit')
    except urllib.error.HTTPError as exc:
        print(f'CareerOps said no ({exc.code}): {exc.read().decode(errors="replace")[:300]}'); return 1
    except urllib.error.URLError as exc:
        print(f'Could not reach CareerOps at {args.careerops}: {exc.reason}. Is it running?'); return 1

    tmp = Path(tempfile.mkdtemp(prefix='careerops-'))
    def save(f):
        if not f: return None
        path = tmp / f['name']; path.write_bytes(base64.b64decode(f['data'])); return str(path)
    facts = build_facts(SimpleNamespace(**kit['profile']), kit['links'], kit['approved'], kit['bank'],
                        save(kit['resume']), save(kit['cover_letter']))

    with sync_playwright() as p:
        browser = None
        for channel in ('chrome', 'msedge', None):
            try:
                browser = p.chromium.launch(headless=False, **({'channel': channel} if channel else {})); break
            except Exception:
                continue
        if browser is None:
            print('No browser found. Run:  py -m playwright install chromium   then try again.'); return 1
        context = browser.new_context(viewport=None, **({'storage_state': kit['storage_state']} if kit.get('storage_state') else {}))
        page = context.new_page()
        page.goto(application_entry_url(kit['url']), wait_until='domcontentloaded', timeout=45000)
        _settle(page)
        print(f"  Filling {kit['company']} - {kit['title']} ...")
        out = prefill(page, facts)
        print(f"\n  Filled {len(out['filled'])} field(s).")
        if out['missing']:
            print('  Still needs you (required):'); [print(f'    - {m}') for m in out['missing']]
        if out['optional']:
            print('  Optional, left blank:'); [print(f'    - {m}') for m in out['optional']]
        print('\n  Check the form in the browser window, fill anything above, then click Submit yourself.')
        input('  When the page says your application was received, come back here and press Enter... ')
        browser.close()

    yes = input('  Did you see a confirmation (thank you / application received)? [y/N] ').strip().lower().startswith('y')
    if yes:
        try:
            call(args.careerops, args.token, f'/api/jobs/{args.job}/mark-applied', 'POST')
            print('  Marked as applied in CareerOps.')
        except Exception as exc:
            print(f'  Could not mark it applied ({exc}). Use "Mark as applied" on the job page.')
    else:
        print('  Not marked. Nothing was recorded as applied.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
