(() => {
  'use strict';
  const scriptURL = document.currentScript?.src || new URL('photo-checklist.js', location.href).href;
  const ITEMS = [
    ['meter', 'Outside', 'Meter closeup', 'Photograph the meter and its number from a safe position.', 'meter'],
    ['surroundings', 'Outside', 'Meter surroundings', 'Step back safely to include the meter wall and nearby space.', 'context'],
    ['left', 'Outside', 'Left of meter', 'Show the wall and space to the left of the meter.', 'context'],
    ['right', 'Outside', 'Right of meter', 'Show the wall and space to the right of the meter.', 'context'],
    ['wall', 'Outside', 'Adjacent wall', 'Include the next wall around the nearest corner and the ground beside it.', 'context'],
    ['fence', 'Outside', 'Behind fence (optional)', 'If safely accessible, show the space behind a fence next to the meter wall.', 'context'],
    ['breaker', 'Electrical', 'Closed breaker box', 'Show the outside of the closed breaker box.', 'panel'],
    ['disconnect', 'Electrical', 'Visible disconnect rating', 'Photograph the amperage label only if it is visible externally. If hidden or unreadable, leave this item without a photo.', 'panel'],
    ['panel-area', 'Electrical', 'Surrounding panel area', 'Step back safely to show where the closed breaker box is located.', 'context']
  ].map(([id, group, label, instruction, example]) => ({ id, group, label, instruction, example }));
  const SAFETY = 'Keep all doors and covers closed, and take photos only when it feels safe.';
  function mount() {
    const root = document.getElementById('photo-checklist');
    if (!root || root.dataset.mounted === 'true') return;
    root.dataset.mounted = 'true';
    const listeners = new AbortController();
    const records = new Map();
    const urls = new Set();
    let address = '', active = ITEMS[0], group = 'Outside', revision = 0, busy = false;
    let pendingURL = null, speech = null, destroyed = false;
    // Speech goes through BaseVoice (speak.js): pre-rendered Kokoro clip, local Kokoro, then the browser voice.
    const voice = () => window.BaseVoice || null;
    function node(tag, className, text) {
      const el = document.createElement(tag);
      if (className) el.className = className;
      if (text !== undefined) el.textContent = text;
      return el;
    }
    function on(el, event, handler) { el.addEventListener(event, handler, { signal: listeners.signal }); }
    function button(text, handler, className = '') {
      const el = node('button', className, text);
      el.type = 'button';
      on(el, 'click', handler);
      return el;
    }
    function revoke(url) { if (url && urls.delete(url)) URL.revokeObjectURL(url); }
    const details = node('details', 'pc-details');
    const summary = node('summary', 'pc-summary', 'More photos');
    const count = node('span', 'pc-count');
    summary.append(count);
    const context = node('p', 'pc-context');
    const privacy = node('p', 'pc-note', 'Your photos stay on this device. Changing homes or leaving the page clears them.');
    const fieldset = node('fieldset', 'pc-controls');
    const legend = node('legend', 'pc-sr-only', 'Photo checklist');
    const groups = node('div', 'pc-groups');
    groups.setAttribute('role', 'group');
    groups.setAttribute('aria-label', 'Photo group');
    const groupButtons = ['Outside', 'Electrical'].map(name => {
      const b = button(name, () => { cancelPending(); stopSpeech(); group = name; active = ITEMS.find(item => item.group === group); message.textContent = ''; render(); });
      groups.append(b);
      return b;
    });
    const label = node('label', 'pc-label', 'Photo');
    const select = node('select', 'pc-select');
    select.id = 'pc-item';
    label.htmlFor = select.id;
    on(select, 'change', () => { cancelPending(); stopSpeech(); active = ITEMS.find(item => item.id === select.value); message.textContent = ''; render(); });
    const instruction = node('p', 'pc-instruction');
    instruction.id = 'pc-instruction';
    const itemStatus = node('p', 'pc-item-status', 'Not started');
    itemStatus.id = 'pc-item-status';
    const safety = node('p', 'pc-safety', SAFETY);
    const media = node('div', 'pc-media');
    const example = node('figure', 'pc-example');
    const exampleImage = node('img');
    exampleImage.width = 480;
    exampleImage.height = 320;
    example.append(exampleImage, node('figcaption', '', 'Illustration, for reference only.'));
    const preview = node('figure', 'pc-preview');
    const previewImage = node('img');
    const previewCaption = node('figcaption');
    preview.append(previewImage, previewCaption);
    media.append(example, preview);
    const fileLabel = node('label', 'pc-upload', 'Take or choose photo');
    const file = node('input', 'pc-file');
    file.id = 'pc-file';
    file.type = 'file';
    file.accept = 'image/jpeg,image/png,image/webp,image/gif,image/avif,image/heic,image/heif';
    file.setAttribute('capture', 'environment');
    file.setAttribute('aria-describedby', 'pc-instruction pc-file-note');
    fileLabel.htmlFor = file.id;
    fileLabel.append(file);
    const fileNote = node('p', 'pc-note', 'Image only, up to 15 MB. Your browser must be able to open it.');
    fileNote.id = 'pc-file-note';
    const actions = node('div', 'pc-actions');
    const remove = button('Remove photo', () => { cancelPending(); revoke(records.get(active.id)?.url); records.delete(active.id); message.textContent = 'Photo removed.'; render(); }, 'pc-remove');
    const unsafe = button('Unable to photograph safely', () => {
      cancelPending();
      const record = records.get(active.id) || {};
      records.set(active.id, { ...record, status: 'Needs review' });
      message.textContent = 'Marked by you as needing review. Nothing has been submitted or requested.';
      render();
    }, 'pc-unsafe');
    const naLabel = node('label', 'pc-na');
    const na = node('input');
    na.type = 'checkbox';
    naLabel.append(na, document.createTextNode('Not applicable'));
    on(na, 'change', () => {
      if (active.id !== 'fence') return;
      cancelPending();
      revoke(records.get(active.id)?.url);
      if (na.checked) records.set(active.id, { status: 'Not applicable' });
      else records.delete(active.id);
      message.textContent = '';
      render();
    });
    actions.append(fileLabel, remove, naLabel, unsafe);
    const reviewLabel = node('label', 'pc-label', 'Your photo status');
    const review = node('select', 'pc-select');
    review.id = 'pc-review';
    reviewLabel.htmlFor = review.id;
    for (const text of ['Captured', 'Needs review', 'Needs another photo']) {
      const option = node('option', '', text); option.value = text; review.append(option);
    }
    on(review, 'change', () => {
      const record = records.get(active.id);
      if (!record?.url) return;
      record.status = review.value;
      message.textContent = 'Status set by you. No review has been requested.';
      render();
    });
    const speechTools = node('div', 'pc-actions');
    const read = button('Read instructions', () => {
      stopSpeech();
      const v = voice();
      if (!v || !address) return;
      // One fixed sentence per photo, so each can be pre-rendered as a clip.
      const mine = speech = {};
      const finish = () => { if (speech === mine) { speech = null; renderSpeech(); } };
      try { v.speak(`${active.label}. ${active.instruction} ${SAFETY}`, { onend: finish }); renderSpeech(); }
      catch { message.textContent = 'The instructions are on screen.'; finish(); }
    });
    const stop = button('Stop reading', stopSpeech);
    speechTools.append(read, stop);
    const message = node('p', 'pc-message');
    message.setAttribute('role', 'status');
    message.setAttribute('aria-live', 'polite');
    const source = node('a', 'pc-source', 'Base photo requirements');
    source.href = 'https://help.basepowercompany.com/en/articles/10280641';
    fieldset.append(legend, groups, label, select, itemStatus, instruction, safety, media, actions, fileNote, reviewLabel, review, speechTools);
    details.append(summary, context, privacy, fieldset, message, source);
    root.replaceChildren(details);

    function renderSpeech() { read.disabled = !voice() || !address; stop.disabled = !speech; }
    function stopSpeech() { if (speech) { speech = null; try { voice()?.stop(); } catch {} } renderSpeech(); }
    function cancelPending() { revision++; busy = false; revoke(pendingURL); pendingURL = null; file.value = ''; }
    function clear() {
      cancelPending(); stopSpeech();
      for (const url of [...urls]) revoke(url);
      records.clear(); previewImage.removeAttribute('src');
    }
    function render() {
      fieldset.disabled = !address;
      fieldset.setAttribute('aria-busy', String(busy));
      context.textContent = address ? `Photos for ${address}` : 'Choose a home before adding photos.';
      const photos = [...records.values()].filter(record => record.url).length;
      const skipped = records.get('fence')?.status === 'Not applicable';
      count.textContent = ` ${photos} ${photos === 1 ? 'photo' : 'photos'}${skipped ? ' / fence not applicable' : ''}`;
      groupButtons.forEach((b, i) => b.setAttribute('aria-pressed', String(['Outside', 'Electrical'][i] === group)));
      select.replaceChildren();
      for (const item of ITEMS.filter(item => item.group === group)) {
        const status = records.get(item.id)?.status || 'Not started';
        const option = node('option', '', `${item.label} - ${status}`);
        option.value = item.id; select.append(option);
      }
      select.value = active.id;
      instruction.textContent = active.instruction;
      const exampleURL = new URL(`assets/guide-${active.example}.png`, scriptURL).href;
      if (exampleImage.src !== exampleURL) exampleImage.src = exampleURL;
      exampleImage.alt = `Example ${active.example === 'meter' ? 'electric meter' : active.example === 'panel' ? 'closed electrical enclosure' : 'space surrounding exterior equipment'}`;
      const record = records.get(active.id);
      itemStatus.textContent = record?.status || 'Not started';
      preview.hidden = !record?.url;
      if (record?.url) {
        if (previewImage.src !== record.url) previewImage.src = record.url;
        previewImage.alt = `Your selected photo: ${active.label}`;
        previewCaption.textContent = record.name;
      } else previewImage.removeAttribute('src');
      naLabel.hidden = active.id !== 'fence';
      na.checked = record?.status === 'Not applicable';
      file.disabled = !address || busy || na.checked;
      fileLabel.classList.toggle('pc-disabled', file.disabled);
      remove.disabled = !record?.url;
      reviewLabel.hidden = review.hidden = !record?.url;
      review.disabled = !record?.url || busy;
      review.value = record?.url ? record.status : 'Captured';
      renderSpeech();
    }
    on(file, 'change', async () => {
      const selected = file.files?.[0];
      file.value = '';
      if (!selected || !address) return;
      cancelPending();
      const token = revision, id = active.id;
      if (!/^image\/(jpeg|png|webp|gif|avif|heic|heif)$/i.test(selected.type) || !selected.size || selected.size > 15 * 1024 * 1024) {
        message.textContent = 'Choose an image no larger than 15 MB. Your existing photo is unchanged.'; render(); return;
      }
      busy = true;
      message.textContent = 'Opening image on this device...';
      const url = URL.createObjectURL(selected); urls.add(url); pendingURL = url;
      render();
      let timer;
      try {
        const image = new Image(); image.src = url;
        await Promise.race([image.decode(), new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('timeout')), 15000); })]);
        if (!image.naturalWidth || !image.naturalHeight) throw new Error('invalid image');
        if (destroyed || token !== revision || !address) { revoke(url); return; }
        revoke(records.get(id)?.url);
        records.set(id, { url, name: selected.name, status: 'Captured' });
        pendingURL = null;
        message.textContent = 'Photo captured in this page. Nothing has been submitted.';
      } catch {
        revoke(url);
        if (token === revision && !destroyed) message.textContent = 'This image could not be opened. Try a JPEG, PNG, or WebP photo. Your existing photo is unchanged.';
      } finally {
        clearTimeout(timer);
        if (token === revision && !destroyed) { pendingURL = null; busy = false; render(); }
      }
    });
    on(document, 'home-context-changed', event => {
      clear();
      address = typeof event.detail?.address === 'string' ? event.detail.address.trim() : '';
      active = ITEMS[0]; group = 'Outside'; message.textContent = ''; render();
    });
    on(document, 'home-photos-reset', () => { clear(); message.textContent = 'Photos cleared from this page.'; render(); });
    on(document, 'home-photos-open', event => {
      cancelPending(); stopSpeech();
      const requested = String(event.detail?.group || '').toLowerCase();
      if (requested === 'electrical' || requested === 'outside') {
        group = requested === 'electrical' ? 'Electrical' : 'Outside';
        active = ITEMS.find(item => item.group === group);
      }
      message.textContent = ''; details.open = true; render();
      if (address) select.focus();
      else summary.focus();
    });
    on(details, 'toggle', () => { if (!details.open) stopSpeech(); });
    on(document, 'visibilitychange', () => { if (document.hidden) stopSpeech(); });
    on(window, 'pagehide', () => { clear(); render(); });
    on(window, 'pageshow', () => { render(); });
    const observer = new MutationObserver(() => {
      if (!root.isConnected) { destroyed = true; clear(); listeners.abort(); observer.disconnect(); }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    render();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
