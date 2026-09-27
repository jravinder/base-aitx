(() => {
  'use strict';
  const base = document.currentScript?.src || new URL('extraction-gallery.js', location.href).href;
  function mount() {
    const root = document.getElementById('extraction-gallery');
    if (!root || root.dataset.mounted === 'true') return;
    root.dataset.mounted = 'true';
    const events = new AbortController();
    const request = new AbortController();
    const states = new Map();
    let examples = [], active = 0, disposed = false;
    const node = (tag, cls, text) => {
      const el = document.createElement(tag);
      if (cls) el.className = cls;
      if (text !== undefined) el.textContent = String(text);
      return el;
    };
    const on = (el, type, fn) => el.addEventListener(type, fn, { signal: events.signal });
    function button(text, fn, cls) {
      const el = node('button', cls, text); el.type = 'button'; on(el, 'click', fn); return el;
    }
    function safeURL(value, local = false) {
      try {
        const url = new URL(value, base);
        if (!['http:', 'https:'].includes(url.protocol)) return null;
        if (local && url.origin !== location.origin) return null;
        return url.href;
      } catch { return null; }
    }
    function link(text, url) {
      const href = typeof url === 'string' && safeURL(url);
      if (!href) return node('span', '', text);
      const a = node('a', '', text); a.href = href; return a;
    }
    const heading = node('h2', '', 'Try a photo');
    heading.id = 'eg-heading'; root.setAttribute('aria-labelledby', heading.id);
    const intro = node('p', 'eg-intro', 'Explore a sample, or check your own photo above.');
    const ownPhoto = button('Use my photo', () => {
      const check = document.getElementById('photo-check');
      if (!check) return;
      check.scrollIntoView({ block: 'nearest' });
      check.querySelector('input,button')?.focus({ preventScroll: true });
    }, 'eg-own-photo');
    const context = node('p', 'eg-context', 'Sample extraction. Unverified sample values; edits stay here, not in your home record.');
    const thumbnails = node('div', 'eg-thumbnails');
    thumbnails.setAttribute('role', 'group'); thumbnails.setAttribute('aria-label', 'Photo examples');
    const body = node('div', 'eg-body');
    const visual = node('div', 'eg-visual');
    const figure = node('figure');
    const image = node('img', 'eg-image');
    const caption = node('figcaption');
    figure.append(image, caption);
    const zoom = button('View full image', () => {
      if (!examples.length || !image.complete || !image.naturalWidth) return;
      enlarged.src = image.src; enlarged.alt = image.alt;
      dialogTitle.textContent = examples[active].title;
      dialog.showModal(); close.focus();
    }, 'eg-zoom');
    const provenance = node('p', 'eg-provenance');
    visual.append(figure, zoom, provenance);
    const panel = node('div', 'eg-panel');
    const title = node('h3');
    const fields = node('div', 'eg-fields');
    const note = node('p', 'eg-note');
    const model = node('p', 'eg-model');
    const actions = node('div', 'eg-actions');
    const confirm = button('Confirm', () => {
      const state = getState();
      if (state.dirty) return;
      state.status = 'Confirmed by you'; updateStatus();
      message.textContent = 'Sample values confirmed by you. Saved here only, not applied to your home.';
    }, 'eg-confirm');
    const correct = button('Correct', () => {
      const state = getState();
      if (!state.dirty) return;
      state.dirty = false; state.status = 'Corrected by you'; updateStatus();
      message.textContent = 'Sample corrections kept in this page only. Saved here only, not applied to your home.';
    });
    const reset = button('Reset sample', () => {
      states.delete(examples[active].id); render(); message.textContent = 'Original saved values restored.';
    });
    actions.append(confirm, correct, reset);
    const status = node('p', 'eg-status'); status.id = 'eg-review-status';
    const message = node('p', 'eg-message'); message.setAttribute('role', 'status');
    panel.append(title, fields, note, model, status, actions);
    body.append(visual, panel);
    const safety = node('p', 'eg-safety', 'For your own photos, keep doors and covers closed and photograph only what you can see safely.');
    const dialog = node('dialog', 'eg-dialog');
    const dialogTitle = node('h3'); dialogTitle.id = 'eg-dialog-title'; dialog.setAttribute('aria-labelledby', dialogTitle.id);
    const close = button('Close image', () => dialog.close());
    const enlarged = node('img');
    dialog.append(dialogTitle, close, enlarged);
    on(dialog, 'close', () => { enlarged.removeAttribute('src'); });
    on(image, 'load', () => { zoom.disabled = false; });
    on(image, 'error', () => { zoom.disabled = true; message.textContent = 'Reload to see the sample photo.'; });
    root.replaceChildren(heading, intro, ownPhoto, context, thumbnails, body, message, safety, dialog);
    body.hidden = thumbnails.hidden = true;
    message.textContent = 'Loading samples...';

    function getState() {
      const example = examples[active];
      if (!states.has(example.id)) states.set(example.id, {
        values: example.fields.map(field => field.value == null ? '' : String(field.value)),
        status: 'To review', dirty: false
      });
      return states.get(example.id);
    }
    function updateStatus() {
      const state = getState();
      status.textContent = state.dirty ? 'Unsaved sample edits' : state.status;
      confirm.disabled = state.dirty; correct.disabled = !state.dirty;
      thumbnails.querySelectorAll('button').forEach((b, index) => {
        b.setAttribute('aria-pressed', String(index === active));
        const item = states.get(examples[index].id);
        b.querySelector('.eg-thumb-status').textContent = item?.dirty ? 'Editing' : item?.status || 'To review';
      });
    }
    function render() {
      const example = examples[active], state = getState();
      title.textContent = example.title;
      if (image.src !== example.imageURL) { zoom.disabled = true; image.src = example.imageURL; }
      image.alt = example.alt;
      caption.textContent = 'Sample photo';
      fields.replaceChildren();
      example.fields.forEach((field, index) => {
        const row = node('div', 'eg-field');
        const label = node('label', '', field.label);
        const input = node('input'); input.type = 'text'; input.id = `eg-field-${index}`;
        input.value = state.values[index]; input.placeholder = 'Not read'; input.autocomplete = 'off';
        input.setAttribute('aria-describedby', 'eg-review-status');
        label.htmlFor = input.id;
        on(input, 'input', () => { state.values[index] = input.value; state.dirty = true; updateStatus(); message.textContent = ''; });
        row.append(label, input);
        if (field.note) {
          const help = node('p', 'eg-field-note', field.note); help.id = `eg-field-note-${index}`;
          input.setAttribute('aria-describedby', `eg-review-status ${help.id}`); row.append(help);
        }
        fields.append(row);
      });
      note.textContent = example.reviewNote || ''; note.hidden = !example.reviewNote;
      model.textContent = example.model ? 'Read on this device.' : '';
      model.hidden = !example.model;
      const source = example.source || {};
      provenance.replaceChildren(link('Photo source', source.url));
      if (source.author) provenance.append(document.createTextNode(` / ${source.author}`));
      if (source.license) provenance.append(document.createTextNode(' / '), link(source.license, source.licenseUrl));
      provenance.append(document.createTextNode(' / Resized; otherwise unchanged.'));
      updateStatus(); message.textContent = '';
    }
    function clearReview() {
      states.clear();
      if (dialog.open) dialog.close();
      if (examples.length) render();
    }
    on(document, 'home-context-changed', clearReview);
    on(document, 'home-photos-reset', clearReview);
    on(window, 'pagehide', clearReview);
    const observer = new MutationObserver(() => {
      if (!root.isConnected) { disposed = true; request.abort(); events.abort(); states.clear(); observer.disconnect(); }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    fetch(new URL('data/photo-examples.json', base), { signal: request.signal }).then(async response => {
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (!Array.isArray(data.examples) || !data.examples.length) throw new Error('empty');
      const ids = new Set();
      examples = data.examples.slice(0, 8).map(example => {
        if (!example || typeof example.id !== 'string' || ids.has(example.id) || typeof example.image !== 'string' || !Array.isArray(example.fields)) throw new Error('invalid sample');
        ids.add(example.id);
        const imageURL = safeURL(example.image, true);
        if (!imageURL || !example.fields.every(field => field && typeof field.label === 'string')) throw new Error('invalid sample');
        return { ...example, imageURL, title: String(example.title || 'Photo example'), alt: String(example.alt || example.title || 'Sample photo') };
      });
      if (disposed) return;
      examples.forEach((example, index) => {
        const b = button('', () => { active = index; render(); }, 'eg-thumbnail');
        const thumb = node('img'); thumb.src = example.imageURL; thumb.alt = ''; thumb.width = 120; thumb.height = 80;
        b.append(thumb, node('span', 'eg-thumb-title', example.title), node('span', 'eg-thumb-status', 'To review'));
        thumbnails.append(b);
      });
      body.hidden = thumbnails.hidden = false; render();
    }).catch(() => {
      if (disposed) return;
      body.hidden = thumbnails.hidden = true;
      message.textContent = 'Samples are unavailable. You can still add your own photos below.';
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
