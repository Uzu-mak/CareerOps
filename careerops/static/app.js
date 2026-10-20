/* CareerOps front end: a small toolkit plus page actions.
   Markup opts in with data attributes: data-action, data-change, data-form, data-open, data-tabs ... */
(() => {
  'use strict';
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const OPTIONS = JSON.parse($('#co-options')?.textContent || '{}');
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ------------------------------------------------------------------ API
  async function api(url, { method = 'GET', json, form, query } = {}) {
    if (query) {
      const qs = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== '' && v !== null && v !== undefined));
      if ([...qs].length) url += (url.includes('?') ? '&' : '?') + qs;
    }
    const opts = { method, headers: {} };
    if (json !== undefined) { opts.body = JSON.stringify(json); opts.headers['Content-Type'] = 'application/json'; }
    if (form) {
      const fd = form instanceof FormData ? form : new FormData();
      if (!(form instanceof FormData)) Object.entries(form).forEach(([k, v]) => fd.append(k, v === null || v === undefined ? '' : v));
      opts.body = fd;
    }
    const res = await fetch(url, opts);
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!res.ok) {
      if (res.status === 401) { location.href = '/auth/login?next=' + encodeURIComponent(location.pathname); }
      const detail = data && typeof data === 'object' ? data.detail : data;
      const msg = Array.isArray(detail) ? detail.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join('; ') : detail;
      throw new Error(msg || `Request failed (${res.status})`);
    }
    return data;
  }

  // ------------------------------------------------------------------ feedback
  function toast(message, { tone = 'good', title = '', timeout = 4500 } = {}) {
    const box = $('#toasts');
    const el = document.createElement('div');
    el.className = `toast ${tone}`;
    el.innerHTML = `<div class="grow">${title ? `<strong>${esc(title)}</strong>` : ''}<span>${esc(message)}</span></div><button type="button" aria-label="Dismiss"><svg class="icon"><use href="#i-x"/></svg></button>`;
    el.querySelector('button').onclick = () => el.remove();
    box.appendChild(el);
    if (timeout) setTimeout(() => el.remove(), timeout);
    return el;
  }
  const fail = (err, title = 'Something went wrong') => toast(err.message || String(err), { tone: 'bad', title, timeout: 9000 });

  function confirmDialog({ title = 'Are you sure?', body = '', ok = 'Confirm', tone = 'primary' } = {}) {
    const dlg = $('#confirmDialog');
    $('[data-confirm-title]', dlg).textContent = title;
    $('[data-confirm-body]', dlg).textContent = body;
    const okBtn = $('[data-confirm-ok]', dlg);
    okBtn.textContent = ok;
    okBtn.className = `btn ${tone}`;
    dlg.returnValue = '';
    dlg.showModal();
    return new Promise((resolve) => dlg.addEventListener('close', () => resolve(dlg.returnValue === 'ok'), { once: true }));
  }

  async function busy(btn, fn) {
    if (!btn || btn.tagName !== 'BUTTON') return fn();
    if (!btn.querySelector('.spinner')) btn.insertAdjacentHTML('afterbegin', '<span class="spinner" aria-hidden="true"></span>');
    btn.classList.add('is-busy'); btn.setAttribute('aria-busy', 'true');
    try { return await fn(); } finally { btn.classList.remove('is-busy'); btn.removeAttribute('aria-busy'); }
  }
  const reload = (ms = 600) => setTimeout(() => location.reload(), ms);

  // ------------------------------------------------------------------ time
  const timeFmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  const dateFmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  function relative(date) {
    const s = Math.round((Date.now() - date.getTime()) / 1000);
    if (s < 45) return 'just now';
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`;
    if (s < 86400 * 7) return `${Math.round(s / 86400)} d ago`;
    return dateFmt.format(date);
  }
  function renderTimes(root = document) {
    $$('time[datetime]', root).forEach((t) => {
      const d = new Date(t.getAttribute('datetime'));
      if (isNaN(d)) return;
      t.title = d.toLocaleString();
      t.textContent = t.dataset.format === 'date' ? dateFmt.format(d) : t.hasAttribute('data-relative') ? relative(d) : timeFmt.format(d);
    });
  }

  // ------------------------------------------------------------------ tag inputs
  function initTagInput(box) {
    const hidden = $('input[type=hidden]', box);
    const input = $('input[type=text]', box);
    const pool = OPTIONS[box.dataset.source] || [];
    let values = JSON.parse(hidden.value || '[]');
    let menu = null; let active = -1;

    const sync = () => { hidden.value = JSON.stringify(values); box.dispatchEvent(new CustomEvent('tags-change', { detail: values })); };
    const render = () => {
      $$('.tag', box).forEach((t) => t.remove());
      values.forEach((v, i) => {
        const tag = document.createElement('span');
        tag.className = 'tag';
        tag.innerHTML = `${esc(v)}<button type="button" aria-label="Remove ${esc(v)}"><svg class="icon" style="width:12px;height:12px"><use href="#i-x"/></svg></button>`;
        tag.querySelector('button').onclick = (e) => { e.stopPropagation(); values.splice(i, 1); render(); sync(); };
        box.insertBefore(tag, input);
      });
    };
    const add = (v) => {
      v = String(v || '').trim().replace(/,$/, '');
      if (!v) return;
      if (!values.some((x) => x.toLowerCase() === v.toLowerCase())) { values.push(v); render(); sync(); }
      input.value = ''; closeMenu();
    };
    const closeMenu = () => { menu?.remove(); menu = null; active = -1; };
    const openMenu = () => {
      const q = input.value.trim().toLowerCase();
      const have = new Set(values.map((x) => x.toLowerCase()));
      const matches = pool.filter((o) => !have.has(o.toLowerCase()) && (!q || o.toLowerCase().includes(q))).slice(0, 12);
      closeMenu();
      if (!matches.length && !q) return;
      menu = document.createElement('div');
      menu.className = 'suggest'; menu.setAttribute('role', 'listbox');
      menu.innerHTML = matches.map((m) => `<button type="button" role="option">${esc(m)}</button>`).join('')
        + (q && !matches.some((m) => m.toLowerCase() === q) ? `<button type="button" role="option" data-custom>Add “${esc(input.value.trim())}”</button>` : '');
      $$('button', menu).forEach((b) => b.addEventListener('mousedown', (e) => { e.preventDefault(); add(b.hasAttribute('data-custom') ? input.value : b.textContent); }));
      box.appendChild(menu);
    };
    input.addEventListener('focus', openMenu);
    input.addEventListener('input', openMenu);
    input.addEventListener('blur', () => setTimeout(closeMenu, 120));
    input.addEventListener('keydown', (e) => {
      const opts = menu ? $$('button', menu) : [];
      if (e.key === 'ArrowDown' && opts.length) { e.preventDefault(); active = (active + 1) % opts.length; }
      else if (e.key === 'ArrowUp' && opts.length) { e.preventDefault(); active = (active - 1 + opts.length) % opts.length; }
      else if (e.key === 'Enter' || e.key === ',' || e.key === 'Tab') {
        if (e.key === 'Tab' && !input.value) return;
        e.preventDefault();
        if (active >= 0 && opts[active]) opts[active].dispatchEvent(new MouseEvent('mousedown'));
        else add(input.value);
        return;
      } else if (e.key === 'Backspace' && !input.value && values.length) { values.pop(); render(); sync(); return; }
      else if (e.key === 'Escape') { closeMenu(); return; }
      opts.forEach((o, i) => o.setAttribute('aria-selected', i === active ? 'true' : 'false'));
    });
    box.addEventListener('click', () => input.focus());
    box.addTag = add;
    box.getValues = () => [...values];
    render();
  }

  // ------------------------------------------------------------------ tabs
  function initTabs(list) {
    const tabs = $$('[role=tab]', list);
    const show = (tab, push) => {
      tabs.forEach((t) => {
        const on = t === tab;
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
        const panel = document.getElementById(t.getAttribute('aria-controls'));
        if (panel) panel.hidden = !on;
      });
      if (push) history.replaceState(null, '', '#' + tab.getAttribute('aria-controls'));
    };
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => show(t, true));
      t.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
          const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
          next.focus(); show(next, true);
        }
      });
    });
    const byHash = () => tabs.find((t) => '#' + t.getAttribute('aria-controls') === location.hash);
    show(byHash() || tabs.find((t) => t.getAttribute('aria-selected') === 'true') || tabs[0], false);
    window.addEventListener('hashchange', () => { const t = byHash(); if (t) { show(t, false); list.scrollIntoView({ behavior: 'smooth', block: 'start' }); } });
  }

  // ------------------------------------------------------------------ helpers for pages
  const fieldValue = (root, name) => {
    const el = root.querySelector(`[name="${name}"]`);
    if (!el) return undefined;
    if (el.type === 'checkbox') return el.checked;
    if (el.type === 'hidden' && el.closest('.tag-input')) return JSON.parse(el.value || '[]');
    if (el.type === 'radio') return root.querySelector(`[name="${name}"]:checked`)?.value ?? null;
    return el.value;
  };
  const numOrNull = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
  const boolOrNull = (v) => (v === 'true' ? true : v === 'false' ? false : null);

  async function saveProfile(patch, { legal = false } = {}) {
    const current = await api('/api/profile');
    const drop = ['id', 'created_at', 'updated_at', 'legal_answers_verified_at', 'baseline_minutes', 'baseline_resume_filename',
      'baseline_resume_path', 'baseline_resume_text', 'baseline_resume_uploaded_at'];
    drop.forEach((k) => delete current[k]);
    if (!legal) ['authorized_to_work_us', 'requires_current_sponsorship', 'requires_future_sponsorship', 'work_authorization_type', 'work_authorization_expiration'].forEach((k) => delete current[k]);
    return api('/api/profile', { method: 'PUT', json: { ...current, ...patch } });
  }

  function showResult(result) {
    const dlg = $('#resultDialog');
    if (!dlg) { toast(result.message || result.status); return; }
    const list = (items, empty) => items && items.length ? `<div class="tag-list">${items.map((x) => `<span class="tag">${esc(x)}</span>`).join('')}</div>` : `<p class="soft">${empty}</p>`;
    const tone = result.submitted ? 'good' : result.manual_fields?.length ? 'warn' : 'info';
    $('[data-result-title]', dlg).textContent = result.submitted ? 'Application submitted' : result.status === 'READY_FOR_SUBMISSION' ? 'Dry run complete — nothing was submitted' : 'Paused for your answers';
    $('[data-result-body]', dlg).innerHTML = `
      <div class="callout ${tone === 'good' ? '' : 'warn'}"><svg class="icon"><use href="#i-${tone === 'good' ? 'check' : 'info'}"/></svg><div>${esc(result.message || '')}${result.confirmation_term ? ` Confirmation: “${esc(result.confirmation_term)}”.` : ''}</div></div>
      <h3 class="eyebrow plain" style="margin:18px 0 8px">Needs you (${(result.manual_fields || []).length})</h3>${list(result.manual_fields, 'Nothing — every required field was answered.')}
      <h3 class="eyebrow plain" style="margin:18px 0 8px">Filled (${(result.filled_fields || []).length})</h3>${list(result.filled_fields, 'No fields were filled.')}
      <h3 class="eyebrow plain" style="margin:18px 0 8px">Uploaded</h3>${list(result.uploaded_files, 'No files uploaded.')}
      ${result.manual_fields?.length ? '<p class="muted" style="margin-top:16px">Answer these in the <strong>Review</strong> tab, then run it again.</p>' : ''}`;
    dlg.showModal();
    dlg.addEventListener('close', () => location.reload(), { once: true });
  }

  // ------------------------------------------------------------------ actions (click)
  const actions = {
    async scan() {
      const t = toast('Checking every enabled source…', { title: 'Scanning', timeout: 0 });
      try {
        const x = await api('/api/discover/run-configured', { method: 'POST' });
        t.remove();
        const errs = (x.errors || []).length;
        toast(`${x.fetched} fetched · ${x.created} new · ${x.analyzed} analyzed${errs ? ` · ${errs} source error(s)` : ''}`, { title: 'Scan complete', tone: errs ? 'warn' : 'good' });
        reload(1600);
      } catch (e) { t.remove(); fail(e, 'Scan failed'); }
    },
    async 'analyze-pending'(btn) {
      const bar = document.getElementById(btn.dataset.progress || '');
      let total = Number(btn.dataset.total || 0) || 1; let done = 0;
      const t = toast('Scoring jobs against your profile…', { title: 'Analyzing', timeout: 0 });
      try {
        for (;;) {
          const x = await api('/api/jobs/analyze-pending', { method: 'POST', query: { limit: 20 } });
          done += x.analyzed; total = Math.max(total, done + x.remaining);
          if (bar) bar.style.width = `${Math.round((done / total) * 100)}%`;
          t.querySelector('span').textContent = `${done} of ${total} analyzed`;
          if (!x.remaining || !x.analyzed) break;
        }
        t.remove(); toast(`${done} job(s) analyzed`, { title: 'Analysis complete' }); reload(900);
      } catch (e) { t.remove(); fail(e, 'Analysis stopped'); }
    },
    async 'analyze-job'(btn) {
      const x = await api(`/api/jobs/${btn.dataset.id}/analyze`, { method: 'POST' });
      toast(`Fit ${Math.round(x.fit_score)}% · ${x.priority} · ${x.action}`, { title: 'Analysis updated' }); reload(800);
    },
    async 'prepare-job'(btn) {
      const x = await api(`/api/jobs/${btn.dataset.id}/prepare`, { method: 'POST' });
      toast(`Resume, cover letter and answers ready${x.review_reasons.length ? ` · ${x.review_reasons.length} to review` : ''}`, { title: 'Package generated' }); reload(900);
    },
    async 'dry-run'(btn) {
      const t = toast('Opening the application and filling it — this can take a minute.', { title: 'Dry run (no submit)', timeout: 0 });
      try { const x = await api(`/api/jobs/${btn.dataset.id}/apply-live`, { method: 'POST', query: { submit: false } }); t.remove(); showResult(x); }
      catch (e) { t.remove(); fail(e, 'Dry run failed'); }
    },
    async apply(btn) {
      const ok = await confirmDialog({
        title: 'Submit this application?',
        body: 'CareerOps will tailor your documents, fill the employer form and submit it. It stops instead of submitting if it meets a CAPTCHA, a sign-in wall or a question you have not answered.',
        ok: 'Apply now',
      });
      if (!ok) return;
      const t = toast('Filling and submitting — this can take a minute.', { title: 'Applying', timeout: 0 });
      try { const x = await api(`/api/jobs/${btn.dataset.id}/apply-live`, { method: 'POST', query: { submit: true } }); t.remove(); showResult(x); }
      catch (e) { t.remove(); fail(e, 'Apply failed'); }
    },
    async simulate(btn) {
      const x = await api(`/api/jobs/${btn.dataset.id}/simulate-apply`, { method: 'POST' });
      showResult({ ...x, status: 'READY_FOR_SUBMISSION' });
    },
    async 'save-review'(btn) {
      const card = btn.closest('.review-q');
      const answer = fieldValue(card, 'answer');
      if (!String(answer || '').trim()) { toast('Choose or type an answer first.', { tone: 'warn' }); return; }
      const x = await api(`/api/applications/${btn.dataset.app}/review-answer`, { method: 'POST', form: { question: card.dataset.question, answer, notes: fieldValue(card, 'notes') || '', resolved: 'true' } });
      card.classList.add('is-done');
      toast(x.remaining ? `${x.remaining} question(s) left` : 'All questions answered — run the application again.', { title: 'Answer saved' });
      if (!x.remaining) reload(1200);
    },
    async 'dismiss-blocker'(btn) {
      const card = btn.closest('.review-q');
      const x = await api(`/api/applications/${btn.dataset.app}/review-answer`, { method: 'POST', form: { question: card.dataset.question, answer: 'dismissed', notes: 'dismissed in review', resolved: 'true' } });
      card.classList.add('is-done'); btn.remove();
      toast(x.remaining ? `${x.remaining} item(s) left` : 'Nothing left to review', { title: 'Dismissed' });
    },
    async 'check-proof'(btn) {
      const x = await api(`/api/applications/${btn.dataset.id}/verification`);
      const msg = { CONFIRMED: `Employer confirmation captured${x.confirmation_term ? ` (“${x.confirmation_term}”)` : ''}.`, UNVERIFIED: 'Marked submitted, but no employer confirmation was captured.', REVIEW: `Waiting on: ${(x.manual_fields || []).join(', ') || 'your review'}.` }[x.state] || 'Not submitted yet.';
      toast(msg, { title: x.state, tone: x.state === 'CONFIRMED' ? 'good' : 'warn', timeout: 8000 });
    },
    async 'delete-source'(btn) {
      if (!(await confirmDialog({ title: `Remove ${btn.dataset.name}?`, body: 'Jobs already found stay; this source just stops being scanned.', ok: 'Remove', tone: 'danger' }))) return;
      await api(`/api/sources/${btn.dataset.id}`, { method: 'DELETE' }); toast('Source removed'); btn.closest('tr')?.remove();
    },
    async 'delete-link'(btn) {
      if (!(await confirmDialog({ title: 'Remove this link?', ok: 'Remove', tone: 'danger' }))) return;
      await api(`/api/profile/links/${btn.dataset.id}`, { method: 'DELETE' }); btn.closest('.list-item')?.remove(); toast('Link removed');
    },
    async 'delete-journal'(btn) {
      if (!(await confirmDialog({ title: 'Delete this entry?', body: 'Its evidence will no longer be used for resumes or fit scoring.', ok: 'Delete', tone: 'danger' }))) return;
      await api(`/api/journal/${btn.dataset.id}`, { method: 'DELETE' }); btn.closest('details')?.remove(); toast('Entry deleted');
    },
    'add-chip'(btn) {
      const box = document.getElementById(btn.dataset.target);
      box?.addTag(btn.textContent.trim()); btn.remove();
    },
    async 'add-all-chips'(btn) {
      const box = document.getElementById(btn.dataset.target);
      $$(`[data-action="add-chip"][data-target="${btn.dataset.target}"]`).forEach((b) => { box.addTag(b.textContent.trim()); b.remove(); });
      btn.closest('.callout')?.remove();
    },
    async 'test-notification'() {
      const x = await api('/api/notifications/test', { method: 'POST' });
      toast(x.ok ? 'Test event sent to every enabled channel.' : 'Notifications are turned off.', { tone: x.ok ? 'good' : 'warn' }); reload(1200);
    },
    async 'poll-alerts'() {
      const imap = await api('/api/alerts/poll-imap', { method: 'POST' });
      const p = await api('/api/alerts/process', { method: 'POST' });
      toast(`${imap.imported || 0} email(s) imported · ${p.created || 0} job(s) created`, { title: 'Inbox checked' }); reload(1200);
    },
    async 'mark-read'(btn) {
      await api(`/api/notifications/${btn.dataset.id}/read`, { method: 'PATCH' });
      const row = btn.closest('.list-item'); row?.classList.remove('unread'); btn.remove();
    },
    async 'mark-all-read'() {
      for (const b of $$('[data-action="mark-read"]')) await api(`/api/notifications/${b.dataset.id}/read`, { method: 'PATCH' });
      toast('All caught up'); reload(500);
    },
    async 'view-artifact'(btn) {
      const x = await api(`/api/artifacts/${btn.dataset.id}`);
      const dlg = $('#artifactDialog');
      $('[data-artifact-title]', dlg).textContent = x.title;
      $('[data-artifact-sub]', dlg).textContent = x.truth_guard_passed ? 'Every claim is backed by your evidence.' : `${(x.blocked_claims || []).length} unverified claim(s) were left out.`;
      $('[data-artifact-body]', dlg).textContent = x.content || '(empty)';
      $('[data-artifact-blocked]', dlg).innerHTML = (x.blocked_claims || []).length
        ? `<h3 class="eyebrow plain" style="margin:16px 0 8px;color:var(--warm)">Withheld — add evidence to include these</h3><div class="stack" style="gap:6px">${x.blocked_claims.map((c) => `<div class="callout warn" style="font-size:12.5px">${esc(c)}</div>`).join('')}</div>` : '';
      dlg.showModal();
    },
    'nav-toggle'() { document.body.classList.toggle('nav-open'); },
  };

  // ------------------------------------------------------------------ change handlers
  const changes = {
    async 'app-status'(el) {
      await api(`/api/applications/${el.dataset.id}/status`, { method: 'PATCH', query: { status: el.value } });
      toast(`Marked ${el.selectedOptions[0].textContent.toLowerCase()}`);
      el.closest('tr')?.setAttribute('data-status', el.value);
    },
    async 'source-enabled'(el) {
      await api(`/api/sources/${el.dataset.id}`, { method: 'PATCH', query: { enabled: el.checked } });
      toast(`${el.dataset.name} ${el.checked ? 'enabled' : 'paused'}`);
    },
    async 'source-interval'(el) {
      await api(`/api/sources/${el.dataset.id}`, { method: 'PATCH', query: { scan_interval_minutes: el.value } });
      toast(`${el.dataset.name}: ${el.selectedOptions[0].textContent.toLowerCase()}`);
    },
    'source-type'(el) {
      const spec = OPTIONS.source_types?.[el.value] || {};
      const form = el.closest('form');
      $('[data-token-label]', form).textContent = spec.field || 'Board / URL';
      $('[name=token_or_url]', form).placeholder = spec.placeholder || '';
      $('[data-key-note]', form).hidden = !spec.key;
    },
    async 'resume-file'(el) {
      const file = el.files?.[0];
      if (!file) return;
      const zone = el.closest('.dropzone');
      zone?.classList.add('is-over');
      const fd = new FormData(); fd.append('resume', file);
      try {
        const x = await api('/api/profile/resume', { method: 'POST', form: fd });
        toast(`${x.characters_extracted.toLocaleString()} characters read${x.skills_added?.length ? ` · ${x.skills_added.length} skills added to your profile` : ` · ${x.skills_detected?.length || 0} skills detected`}`, { title: 'Master resume saved' });
        reload(1200);
      } catch (e) { fail(e, 'Upload failed'); } finally { zone?.classList.remove('is-over'); el.value = ''; }
    },
  };

  // ------------------------------------------------------------------ forms
  const forms = {
    async 'profile-identity'(f) {
      await saveProfile({
        full_name: fieldValue(f, 'full_name'), preferred_name: fieldValue(f, 'preferred_name') || null, email: fieldValue(f, 'email') || null,
        phone: fieldValue(f, 'phone') || null, home_location: fieldValue(f, 'home_location') || null,
        linkedin_url: fieldValue(f, 'linkedin_url') || null, github_url: fieldValue(f, 'github_url') || null,
      });
      toast('Identity saved');
    },
    async 'profile-search'(f) {
      await saveProfile({
        role_families: fieldValue(f, 'role_families'), skills: fieldValue(f, 'skills'), preferred_locations: fieldValue(f, 'preferred_locations'),
        search_radius_miles: Number(fieldValue(f, 'search_radius_miles') || 50),
        remote_allowed: fieldValue(f, 'remote_allowed'), hybrid_allowed: fieldValue(f, 'hybrid_allowed'), onsite_allowed: fieldValue(f, 'onsite_allowed'),
        minimum_salary: numOrNull(fieldValue(f, 'minimum_salary')), target_salary: numOrNull(fieldValue(f, 'target_salary')),
        years_professional_software: Number(fieldValue(f, 'years_professional_software') || 0),
        years_hands_on_software: Number(fieldValue(f, 'years_hands_on_software') || 0),
        eeo_preference: fieldValue(f, 'eeo_preference') || null,
      });
      toast('Search preferences saved — re-run analysis to rescore jobs.');
    },
    async 'profile-legal'(f) {
      const values = {
        authorized_to_work_us: boolOrNull(fieldValue(f, 'authorized_to_work_us')),
        requires_current_sponsorship: boolOrNull(fieldValue(f, 'requires_current_sponsorship')),
        requires_future_sponsorship: boolOrNull(fieldValue(f, 'requires_future_sponsorship')),
        work_authorization_type: fieldValue(f, 'work_authorization_type') || null,
        work_authorization_expiration: fieldValue(f, 'work_authorization_expiration') || null,
      };
      if ([values.authorized_to_work_us, values.requires_current_sponsorship, values.requires_future_sponsorship].some((v) => v === null)) {
        toast('Answer all three Yes/No questions before verifying.', { tone: 'warn' }); return;
      }
      const ok = await confirmDialog({ title: 'Verify these answers?', body: 'CareerOps will give exactly these answers to work-authorization and sponsorship questions on every application.', ok: 'Verify & save' });
      if (!ok) return;
      await saveProfile(values, { legal: true });
      toast('Work-authorization answers verified'); reload(900);
    },
    async 'add-link'(f) {
      await api('/api/profile/links', { method: 'POST', form: { label: fieldValue(f, 'label'), url: fieldValue(f, 'url'), link_type: fieldValue(f, 'link_type'), include_in_applications: 'true' } });
      toast('Link added'); reload(500);
    },
    async journal(f) {
      const form = {};
      ['entry_date', 'title', 'project', 'what_built', 'problem_solved', 'architecture_decisions', 'tradeoffs', 'time_spent_hours', 'impact', 'metrics_text', 'links_text', 'lessons']
        .forEach((k) => { form[k] = fieldValue(f, k) || ''; });
      form.skills_text = (fieldValue(f, 'skills') || []).join('\n');
      const x = await api('/api/journal', { method: 'POST', form });
      toast(`Saved as evidence #${x.evidence_id}`, { title: 'Journal entry added' }); reload(700);
    },
    async 'add-source'(f) {
      const body = { source_type: fieldValue(f, 'source_type'), name: fieldValue(f, 'name'), token_or_url: fieldValue(f, 'token_or_url'), enabled: 'true', scan_interval_minutes: fieldValue(f, 'scan_interval_minutes') };
      await api('/api/sources', { method: 'POST', form: body });
      f.closest('dialog')?.close();
      toast(`${body.name} added — scanning now`); await actions.scan();
    },
    async 'add-job'(f) {
      const x = await api('/api/jobs/manual', { method: 'POST', json: {
        company: fieldValue(f, 'company'), title: fieldValue(f, 'title'), location: fieldValue(f, 'location') || null,
        workplace_type: fieldValue(f, 'workplace_type') || null, description: fieldValue(f, 'description'),
        application_url: fieldValue(f, 'application_url') || null, canonical_url: fieldValue(f, 'application_url') || null,
      } });
      await api(`/api/jobs/${x.job_id}/analyze`, { method: 'POST' });
      location.href = `/jobs/${x.job_id}`;
    },
    async autopilot(f) {
      await api('/api/runtime-settings', { method: 'PUT', form: { auto_apply_enabled: fieldValue(f, 'auto_apply_enabled') ? 'true' : 'false', auto_apply_min_fit: fieldValue(f, 'auto_apply_min_fit'), max_auto_applications_per_day: fieldValue(f, 'max_auto_applications_per_day') } });
      toast(`Autopilot ${fieldValue(f, 'auto_apply_enabled') ? 'on' : 'off'}`, { title: 'Saved' });
    },
    async notifications(f) {
      const form = {};
      ['enabled', 'notify_new_match', 'notify_high_fit', 'notify_human_review', 'notify_submitted', 'notify_failed', 'email_enabled', 'slack_enabled', 'discord_enabled', 'telegram_enabled']
        .forEach((k) => { form[k] = fieldValue(f, k) ? 'true' : 'false'; });
      ['minimum_fit_score', 'urgent_fit_score', 'email_to', 'slack_webhook_url', 'discord_webhook_url', 'telegram_bot_token', 'telegram_chat_id']
        .forEach((k) => { form[k] = fieldValue(f, k) || ''; });
      await api('/api/notifications/preferences', { method: 'PUT', form });
      toast('Notification settings saved');
    },
    async 'ingest-alert'(f) {
      const x = await api('/api/alerts/email', { method: 'POST', form: { provider: fieldValue(f, 'provider'), subject: fieldValue(f, 'subject'), text: fieldValue(f, 'text') } });
      await api('/api/alerts/process', { method: 'POST' });
      toast(`${x.urls.length} job link(s) found and queued`, { title: 'Alert imported' }); reload(1000);
    },
  };

  // ------------------------------------------------------------------ wiring
  document.addEventListener('click', async (e) => {
    const opener = e.target.closest('[data-open]');
    if (opener) { e.preventDefault(); document.getElementById(opener.dataset.open)?.showModal(); return; }
    const closer = e.target.closest('[data-close]');
    if (closer) { e.preventDefault(); closer.closest('dialog')?.close(); return; }
    if (e.target.closest('[data-nav-toggle]')) { actions['nav-toggle'](); return; }
    if (document.body.classList.contains('nav-open') && !e.target.closest('.sidebar')) document.body.classList.remove('nav-open');
    const el = e.target.closest('[data-action]');
    if (el && actions[el.dataset.action]) {
      e.preventDefault();
      try { await busy(el, () => actions[el.dataset.action](el)); } catch (err) { fail(err); }
      return;
    }
    const row = e.target.closest('tr[data-href]');
    if (row && !e.target.closest('a, button, select, input, label')) {
      if (e.metaKey || e.ctrlKey) window.open(row.dataset.href, '_blank'); else location.href = row.dataset.href;
    }
  });
  document.addEventListener('change', async (e) => {
    const el = e.target.closest('[data-change]');
    if (el && changes[el.dataset.change]) { try { await changes[el.dataset.change](el); } catch (err) { fail(err); } }
    const out = e.target.matches('input[type=range][data-output]') && document.getElementById(e.target.dataset.output);
    if (out) out.value = e.target.value;
  });
  document.addEventListener('input', (e) => {
    if (e.target.matches('input[type=range][data-output]')) { const out = document.getElementById(e.target.dataset.output); if (out) out.value = e.target.value; }
  });
  document.addEventListener('submit', async (e) => {
    const f = e.target.closest('form[data-form]');
    if (!f || !forms[f.dataset.form]) return;
    e.preventDefault();
    if (!f.reportValidity()) return;
    const btn = e.submitter || $('button[type=submit]', f);
    try { await busy(btn, () => forms[f.dataset.form](f)); } catch (err) { fail(err, 'Not saved'); }
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') document.body.classList.remove('nav-open'); });

  // drag & drop on resume dropzones
  $$('.dropzone').forEach((zone) => {
    const input = $('input[type=file]', zone);
    zone.addEventListener('click', (e) => { if (e.target !== input) input.click(); });
    zone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    ['dragenter', 'dragover'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove('is-over'); }));
    zone.addEventListener('drop', (e) => { if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; input.dispatchEvent(new Event('change', { bubbles: true })); } });
  });

  $$('input[type=date][data-today]').forEach((el) => { if (!el.value) { const d = new Date(); el.value = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); } });
  $$('.tag-input').forEach(initTagInput);
  $$('[data-tabs]').forEach(initTabs);
  $$('[data-change="source-type"]').forEach((el) => changes['source-type'](el));
  $$('[data-greeting]').forEach((el) => { const h = new Date().getHours(); el.textContent = h < 5 ? 'Working late' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'; });
  renderTimes();

  // ------------------------------------------------------------------ jobs table
  const jobsRoot = $('#jobsBrowser');
  if (jobsRoot) {
    const form = $('#jobFilters', jobsRoot);
    const body = $('tbody', jobsRoot);
    const pager = $('[data-pager]', jobsRoot);
    const count = $('[data-count]', jobsRoot);
    const params = new URLSearchParams(location.search);
    [...form.elements].forEach((el) => { if (el.name && params.has(el.name)) el.value = params.get(el.name); });
    let page = Number(params.get('page') || 1); let timer = null; let seq = 0;

    const fitClass = (s) => (s >= 80 ? 'high' : s >= 60 ? 'mid' : 'low');
    const rowHtml = (j) => `
      <tr data-href="/jobs/${j.id}">
        <td class="primary-cell"><strong>${esc(j.title)}</strong><span>${esc(j.company)}</span></td>
        <td class="hide-sm">${esc(j.location || '—')}${j.workplace_type ? ` <span class="badge neutral">${esc(j.workplace_type)}</span>` : ''}</td>
        <td>${j.fit_score === null ? '<span class="soft">—</span>' : `<span class="fit ${fitClass(j.fit_score)}"><span class="fit-bar"><i style="width:${j.fit_score}%"></i></span>${j.fit_score}%</span>`}</td>
        <td class="nowrap">${j.action ? `<span class="badge ${j.action.toLowerCase()}">${esc(j.action)}</span> <span class="soft mono">${esc(j.priority || '')}</span>` : '<span class="badge neutral">Not analyzed</span>'}</td>
        <td class="hide-sm">${j.application_status ? `<span class="badge info">${esc(j.application_status)}</span>` : '<span class="soft">—</span>'}</td>
        <td class="hide-sm soft"><time datetime="${esc(j.first_seen_at || '')}" data-relative></time></td>
        <td class="actions-cell"><a class="btn sm" href="/jobs/${j.id}">Open</a></td>
      </tr>`;

    async function load() {
      const query = Object.fromEntries([...new FormData(form)].filter(([, v]) => v !== ''));
      query.page = page;
      const url = new URLSearchParams(query); if (page === 1) url.delete('page');
      history.replaceState(null, '', location.pathname + (String(url) ? '?' + url : ''));
      const mine = ++seq;
      body.innerHTML = Array.from({ length: 6 }, () => '<tr><td colspan="7"><div class="skeleton" style="width:60%"></div></td></tr>').join('');
      try {
        const data = await api('/api/jobs/search', { query });
        if (mine !== seq) return;
        page = data.page;
        count.textContent = `${data.total.toLocaleString()} job${data.total === 1 ? '' : 's'}`;
        body.innerHTML = data.items.length ? data.items.map(rowHtml).join('')
          : `<tr><td colspan="7"><div class="empty"><svg class="icon"><use href="#i-search"/></svg><strong>No jobs match these filters</strong><span>Clear a filter or run a scan.</span></div></td></tr>`;
        pager.innerHTML = `<span>Page ${data.page} of ${data.pages}</span><div class="actions">
          <button class="btn sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}><svg class="icon"><use href="#i-arrow-left"/></svg>Previous</button>
          <button class="btn sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next<svg class="icon"><use href="#i-arrow-right"/></svg></button></div>`;
        renderTimes(body);
      } catch (e) { fail(e, 'Could not load jobs'); }
    }
    form.addEventListener('input', (e) => { if (e.target.name === 'q') { clearTimeout(timer); timer = setTimeout(() => { page = 1; load(); }, 250); } });
    form.addEventListener('change', (e) => { if (e.target.name !== 'q') { page = 1; load(); } });
    form.addEventListener('submit', (e) => { e.preventDefault(); page = 1; load(); });
    pager.addEventListener('click', (e) => { const b = e.target.closest('[data-page]'); if (b && !b.disabled) { page = Number(b.dataset.page); load(); jobsRoot.scrollIntoView({ behavior: 'smooth' }); } });
    $$('[data-preset]', jobsRoot).forEach((b) => b.addEventListener('click', () => {
      const [k, v] = b.dataset.preset.split('='); form.elements[k].value = form.elements[k].value === v ? '' : v; page = 1; load();
    }));
    $('[data-reset]', jobsRoot)?.addEventListener('click', () => { form.reset(); [...form.elements].forEach((el) => { if (el.name) el.value = el.tagName === 'SELECT' ? (el.dataset.default || '') : ''; }); page = 1; load(); });
    load();
  }

  // ------------------------------------------------------------------ client-side filters (applications)
  $$('[data-filter-group]').forEach((group) => {
    const target = document.getElementById(group.dataset.filterGroup);
    group.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-filter]');
      if (!b) return;
      $$('button', group).forEach((x) => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
      const v = b.dataset.filter;
      $$('[data-status]', target).forEach((row) => { row.hidden = v !== 'all' && !v.split(',').includes(row.dataset.status); });
    });
  });

  // /applications#review etc. pre-selects that status filter
  const hashFilter = location.hash && document.getElementById('filter-' + location.hash.slice(1));
  if (hashFilter) hashFilter.click();

  window.CareerOps = { api, toast, confirm: confirmDialog };
})();
