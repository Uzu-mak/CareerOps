// CareerOps form scanner. Evaluated inside every frame of an application page.
//
// One entry point, dispatched on req.op:
//   scan    -> visible form fields, buttons and page signals (CAPTCHA, password, errors)
//   options -> currently visible listbox options (custom dropdowns / comboboxes)
//   check   -> tick a radio/checkbox by id, even when the native input is visually hidden
//   click   -> DOM click by id (fallback when a pointer click is intercepted)
//   text    -> the frame's visible text (confirmation detection)
//
// Every element the agent may act on gets a stable data-careerops-id so the
// Python side can address it with a plain CSS selector.
(req) => {
  req = req || {};
  const ATTR = 'data-careerops-id';
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const byId = (id) => document.querySelector(`[${ATTR}="${String(id).replace(/"/g, '')}"]`);

  const tag = (el) => {
    let id = el.getAttribute(ATTR);
    if (!id) {
      const root = document.documentElement;
      const n = Number(root.getAttribute('data-careerops-seq') || '0') + 1;
      root.setAttribute('data-careerops-seq', String(n));
      id = 'c' + n;
      el.setAttribute(ATTR, id);
    }
    return id;
  };

  const visible = (el) => {
    if (!el || !el.isConnected) return false;
    if (el.checkVisibility && !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };

  // Text of a label-like node without the text of controls nested in it
  // (a <select> inside a <label> would otherwise leak every option into the label).
  const textOf = (node) => {
    if (!node) return '';
    const c = node.cloneNode(true);
    // Drop controls plus widget chatter that lives inside labels on some ATSs
    // (Lever: "No location found…", "Analyzing resume… Success!").
    c.querySelectorAll('input,select,textarea,option,button,script,style,svg,[hidden],[aria-live],[role="status"],[role="alert"],[role="listbox"],'
      + '[class*="error" i],[class*="loading" i],[class*="spinner" i],[class*="dropdown" i],[class*="result" i],[class*="filename" i],[class*="status" i],[class*="hint" i]')
      .forEach((n) => n.remove());
    return clean(c.textContent);
  };
  const STAR = /[*✱]/;
  const requiredClass = (node) => {
    const cls = String((node && node.className && node.className.baseVal !== undefined ? node.className.baseVal : node && node.className) || '');
    return /(^|[\s_-])required/i.test(cls) && !/not[-_]?required|optional/i.test(cls);
  };
  const labelFrom = (node) => {
    if (!node) return null;
    if (typeof node === 'string') return { text: clean(node), star: STAR.test(node), cls: false };
    return { text: textOf(node), star: STAR.test(node.textContent || ''), cls: requiredClass(node) };
  };
  const byIds = (ids) => {
    const parts = String(ids || '').split(/\s+/).filter(Boolean).map((id) => document.getElementById(id)).filter(Boolean);
    if (!parts.length) return null;
    return {
      text: clean(parts.map(textOf).join(' ')),
      star: parts.some((p) => STAR.test(p.textContent || '')),
      cls: parts.some(requiredClass),
    };
  };

  // Nearest preceding text block that describes a control or a group of controls:
  // a fieldset legend, an ARIA group label, or the first text-only sibling that
  // comes before the subtree holding the controls (Lever/Ashby/Greenhouse layouts).
  const describe = (controls) => {
    let node = controls[0].parentElement;
    for (let depth = 0; node && depth < 7; depth += 1, node = node.parentElement) {
      if (node === document.body || node.tagName === 'FORM') break;
      if (node.tagName === 'FIELDSET') {
        const legend = node.querySelector('legend');
        if (legend && textOf(legend)) return labelFrom(legend);
      }
      const role = node.getAttribute('role');
      if (role === 'radiogroup' || role === 'group') {
        if (node.getAttribute('aria-labelledby')) {
          const l = byIds(node.getAttribute('aria-labelledby'));
          if (l && l.text) return l;
        }
        if (node.getAttribute('aria-label')) return labelFrom(node.getAttribute('aria-label'));
      }
      for (const child of node.children) {
        if (controls.some((c) => child === c || child.contains(c))) break;
        if (child.matches('script,style,template,input,select,textarea,button,a,[role="button"]')) continue;
        if (child.querySelector('input,select,textarea,button')) continue;
        const t = textOf(child);
        if (t && t.length <= 400) return labelFrom(child);
      }
    }
    return null;
  };

  const labelFor = (el) => {
    if (el.labels && el.labels.length) {
      const lab = el.labels[0];
      // A <label> wrapping the whole question (label text + field + widget): use its title part.
      if (lab.contains(el)) {
        const title = [...lab.querySelectorAll('[class*="label" i], [class*="question" i], [class*="title" i]')]
          .find((n) => !n.contains(el) && !n.querySelector('input,select,textarea') && textOf(n));
        if (title) { const l = labelFrom(title); l.star = l.star || STAR.test(lab.textContent || ''); return l; }
      }
      const l = labelFrom(lab);
      if (l.text) return l;
    }
    if (el.getAttribute('aria-labelledby')) {
      const l = byIds(el.getAttribute('aria-labelledby'));
      if (l && l.text) return l;
    }
    if (el.getAttribute('aria-label')) return labelFrom(el.getAttribute('aria-label'));
    const d = describe([el]);
    if (d && d.text) return d;
    if (el.getAttribute('placeholder')) return labelFrom(el.getAttribute('placeholder'));
    return labelFrom(el.getAttribute('name') || '');
  };

  const isRequired = (el, label) =>
    !!(el.required || el.getAttribute('aria-required') === 'true' || (label && (label.star || label.cls)) ||
       (label && /\(required\)/i.test(label.text)));

  const finalLabel = (label) => clean((label && label.text || '').replace(/[*✱]/g, '').replace(/\(required\)/ig, ''));

  const comboValue = (el) => {
    if (el.value) return clean(el.value);
    const box = el.parentElement && el.parentElement.closest('[class*="container" i], [class*="select" i], [class*="combobox" i], [class*="dropdown" i]');
    const shown = box && box.querySelector('[class*="single-value" i], [class*="singleValue" i], [class*="selected-value" i], [class*="multi-value__label" i]');
    return shown ? clean(shown.textContent) : '';
  };

  const errorsNear = (el) => {
    if (el.getAttribute('aria-invalid') === 'true') return true;
    try { return el.matches(':user-invalid'); } catch (e) { return false; }
  };

  const scan = () => {
    const fields = [];
    const groups = new Map();
    const controls = document.querySelectorAll('input, select, textarea, [role="combobox"]:not(input), [role="radio"]:not(input)');
    for (const el of controls) {
      const t = (el.getAttribute('type') || '').toLowerCase();
      const tagName = el.tagName.toLowerCase();
      if (['hidden', 'submit', 'button', 'image', 'reset', 'search'].includes(t)) continue;
      if (t === 'password') continue; // reported as a signal, never filled
      if (el.closest('[data-careerops-ignore]')) continue;
      if (el.getAttribute('role') === 'combobox' && tagName !== 'input' && el.querySelector('input')) continue;

      if (t === 'radio' || t === 'checkbox' || el.getAttribute('role') === 'radio') {
        const shown = visible(el) || (el.labels && [...el.labels].some(visible));
        if (!shown) continue;
        const rg = el.getAttribute('role') === 'radio' ? el.closest('[role="radiogroup"]') : null;
        const key = rg ? 'rg:' + tag(rg) : (t || 'radio') + ':' + (el.name || tag(el));
        if (!groups.has(key)) groups.set(key, { kind: t || 'radio', members: [] });
        groups.get(key).members.push(el);
        continue;
      }

      if (t === 'file') {
        const label = labelFor(el);
        fields.push({
          id: tag(el), type: 'file', label: finalLabel(label), required: isRequired(el, label),
          value: el.files && el.files.length ? el.files[0].name : '', accept: el.getAttribute('accept') || '',
          name: el.name || '', invalid: errorsNear(el),
        });
        continue;
      }
      if (!visible(el) || el.disabled || el.readOnly && tagName !== 'select' && el.getAttribute('role') !== 'combobox') continue;

      const label = labelFor(el);
      const base = {
        id: tag(el), label: finalLabel(label), required: isRequired(el, label), name: el.name || '',
        autocomplete: el.getAttribute('autocomplete') || '', invalid: errorsNear(el),
      };
      if (tagName === 'select') {
        const opts = [...el.options].map((o) => ({
          value: o.value, text: clean(o.textContent),
          placeholder: o.value === '' || /^(select|choose|please select|--|—)/i.test(clean(o.textContent)),
        }));
        const sel = el.selectedOptions && el.selectedOptions[0];
        const value = sel && !(sel.value === '' || /^(select|choose|please select|--|—)/i.test(clean(sel.textContent))) ? clean(sel.textContent) : '';
        fields.push({ ...base, type: 'select', options: opts, value, multiple: !!el.multiple });
      } else if (el.getAttribute('role') === 'combobox' || el.getAttribute('aria-autocomplete') === 'list') {
        fields.push({ ...base, type: 'combobox', value: comboValue(el) });
      } else if (tagName === 'textarea') {
        fields.push({ ...base, type: 'textarea', value: el.value || '' });
      } else {
        fields.push({ ...base, type: t || 'text', value: el.value || '' });
      }
    }

    for (const [, g] of groups) {
      const members = g.members;
      const optionText = (m) => {
        if (m.labels && m.labels.length) return textOf(m.labels[0]);
        if (m.getAttribute('aria-label')) return clean(m.getAttribute('aria-label'));
        return textOf(m) || clean(m.value);
      };
      const checked = (m) => (m.tagName === 'INPUT' ? m.checked : m.getAttribute('aria-checked') === 'true');
      if (g.kind === 'checkbox' && members.length === 1) {
        const el = members[0];
        const label = labelFor(el);
        fields.push({
          id: tag(el), type: 'checkbox', label: finalLabel(label), required: isRequired(el, label),
          value: el.checked ? 'checked' : '', options: [], name: el.name || '', invalid: errorsNear(el),
        });
        continue;
      }
      const label = describe(members) || labelFor(members[0]);
      fields.push({
        id: tag(members[0]) + 'g', type: g.kind === 'checkbox' ? 'checkbox_group' : 'radio',
        label: finalLabel(label),
        required: members.some((m) => m.required || m.getAttribute('aria-required') === 'true') || !!(label && (label.star || label.cls)),
        options: members.map((m) => ({ id: tag(m), text: optionText(m) })),
        value: members.filter(checked).map(optionText).join(', '), name: members[0].name || '',
        invalid: members.some(errorsNear),
      });
    }

    // Yes/No rendered as two plain buttons (Ashby boolean questions).
    const seenParents = new Set();
    for (const b of document.querySelectorAll('button')) {
      const p = b.parentElement;
      if (!p || seenParents.has(p) || !visible(b)) continue;
      const btns = [...p.children].filter((c) => c.tagName === 'BUTTON');
      const texts = btns.map((c) => clean(c.textContent).toLowerCase());
      if (btns.length !== 2 || !(texts.includes('yes') && texts.includes('no'))) continue;
      seenParents.add(p);
      const label = describe([p]);
      const on = btns.find((c) => c.getAttribute('aria-pressed') === 'true' || /(^|[\s_-])(active|selected|checked)/i.test(String(c.className)));
      fields.push({
        id: tag(p) + 'b', type: 'buttons', label: finalLabel(label), required: !!(label && (label.star || label.cls)),
        options: btns.map((c) => ({ id: tag(c), text: clean(c.textContent) })), value: on ? clean(on.textContent) : '',
        name: '', invalid: false,
      });
    }

    const buttons = [];
    for (const b of document.querySelectorAll('button, input[type="submit"], input[type="button"], a, [role="button"]')) {
      if (buttons.length >= 250 || !visible(b)) continue;
      const text = clean(b.tagName === 'INPUT' ? b.value : (b.textContent || b.getAttribute('aria-label')));
      if (!text || text.length > 80) continue;
      buttons.push({ id: tag(b), text, tag: b.tagName.toLowerCase(), type: (b.getAttribute('type') || '').toLowerCase(), disabled: !!b.disabled });
    }

    // Only a challenge the candidate must actually solve counts as a CAPTCHA.
    // The invisible reCAPTCHA badge and its anchor frame are present on most
    // Greenhouse/Lever pages and are not a blocker.
    let captcha = false;
    for (const f of document.querySelectorAll('iframe')) {
      const src = String(f.getAttribute('src') || '').toLowerCase();
      const title = String(f.getAttribute('title') || '').toLowerCase();
      if (!visible(f)) continue;
      const r = f.getBoundingClientRect();
      if (r.width < 60 || r.height < 60 || r.bottom < 0) continue;
      if (f.closest('.grecaptcha-badge')) continue;
      const challenge = /recaptcha\/(api2|enterprise)\/bframe|hcaptcha.*challenge|challenges\.cloudflare\.com|arkoselabs|funcaptcha/.test(src) || /recaptcha challenge|hcaptcha challenge/.test(title);
      const checkbox = /recaptcha\/(api2|enterprise)\/anchor/.test(src) && !/size=invisible/.test(src);
      const hcheck = /hcaptcha/.test(src) && /frame=checkbox/.test(src);
      if (challenge || checkbox || hcheck) captcha = true;
    }

    const errors = [];
    for (const e of document.querySelectorAll('[role="alert"], [aria-live="assertive"], .error, .errors, [class*="error-message" i], [class*="field-error" i], [class*="_error" i]')) {
      if (!visible(e)) continue;
      const t = clean(e.textContent);
      if (t && t.length <= 240 && !errors.includes(t)) errors.push(t);
      if (errors.length >= 10) break;
    }

    const embed = document.querySelector('iframe#grnhse_iframe, iframe[src*="greenhouse.io/embed"], iframe[src*="boards.greenhouse.io"], iframe[src*="job-boards.greenhouse.io"]');
    return {
      url: location.href,
      fields,
      buttons,
      captcha,
      password: [...document.querySelectorAll('input[type="password"]')].some(visible),
      errors,
      embed: embed ? embed.src : null,
      text: clean(document.body ? document.body.innerText : '').toLowerCase().slice(0, 40000),
    };
  };

  if (req.op === 'scan') return scan();
  if (req.op === 'text') return clean(document.body ? document.body.innerText : '').toLowerCase().slice(0, 40000);
  if (req.op === 'options') {
    const out = [];
    const sel = '[role="option"], [class*="select__option" i], [class*="option" i][id*="option" i], li[id*="option" i], '
      + '[class*="dropdown-location" i], [class*="dropdown-results" i] > *, [class*="autocomplete" i] li, [class*="suggestion" i]';
    for (const o of document.querySelectorAll(sel)) {
      if (!visible(o) || out.length >= 200) continue;
      const text = clean(o.textContent);
      if (text) out.push({ id: tag(o), text });
    }
    return out;
  }
  if (req.op === 'check') {
    const el = byId(req.id);
    if (!el) return false;
    const isOn = () => (el.tagName === 'INPUT' ? el.checked : el.getAttribute('aria-checked') === 'true');
    if (isOn() !== (req.on !== false)) el.click();
    return isOn() === (req.on !== false);
  }
  if (req.op === 'click') {
    const el = byId(req.id);
    if (!el) return false;
    el.click();
    return true;
  }
  return null;
}
