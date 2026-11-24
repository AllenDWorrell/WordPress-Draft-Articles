const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness() {
  const elements = new Map();
  const listeners = new Map();
  const timers = new Map();
  const requests = [];
  let timerId = 0;
  const document = { activeElement: null };
  document.createElement = tag => ({
    tagName: tag.toUpperCase(),
    textContent: '',
    innerHTML: '',
    className: '',
    children: [],
    childNodes: [],
    append(...nodes) { this.children.push(...nodes); },
  });
  function element(id) {
    if (elements.has(id)) return elements.get(id);
    const node = {
      textContent: '', hidden: false, dataset: {}, attributes: {}, children: [],
      addEventListener() {},
      append(...nodes) { this.children.push(...nodes); },
      replaceChildren(...nodes) { this.children = [...nodes]; },
      setAttribute(name, value) { this.attributes[name] = value; },
      contains(other) { return this.children.includes(other); },
      focus() { document.activeElement = this; },
      setSelectionRange() {},
      querySelectorAll(selector) { return selector === 'button' ? this.children : []; },
      set innerHTML(html) {
        this.html = html;
        this.children = [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].map(match => {
          const attributes = Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(a => [a[1], a[2]]));
          return {
            attributes, dataset: { id: attributes['data-id'] }, html: match[2],
            textContent: match[2].replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim(),
            focus() { document.activeElement = this; },
          };
        });
      },
      get innerHTML() { return this.html || ''; },
    };
    elements.set(id, node);
    return node;
  }
  document.getElementById = element;
  document.querySelector = selector => selector.startsWith('meta') ? { content: 'test-token' } : element(selector);
  const context = vm.createContext({
    document, structuredClone,
    window: { addEventListener: (type, listener) => listeners.set(type, listener) },
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
    clearTimeout: id => timers.delete(id),
    fetch: (url, options) => new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })),
  });
  const source = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');
  assert.match(source, /\binit\(\);\s*$/);
  vm.runInContext(source.replace(/\binit\(\);\s*$/, ''), context);
  vm.runInContext('syncTags = () => {}; project = {articles: []};', context);
  const run = code => vm.runInContext(code, context);
  const unloadBlocked = () => {
    const event = { prevented: false, preventDefault() { this.prevented = true; } };
    listeners.get('beforeunload')(event);
    return event.prevented;
  };
  const flush = () => new Promise(resolve => setImmediate(resolve));
  const succeed = request => request.resolve({ ok: true, json: async () => ({}) });
  return { run, element, timers, requests, unloadBlocked, flush, succeed };
}

test('an older save response cannot mark newer edits saved or remove the unload warning', async () => {
  const h = harness();
  h.run('queueSave()');
  const firstSave = h.run('saveNow()');
  await h.flush();
  assert.equal(h.requests.length, 1);
  h.run('queueSave()');
  const secondSave = h.run('saveNow()');
  h.succeed(h.requests[0]);
  await firstSave;
  assert.equal(h.element('saveState').textContent, 'Unsaved changes');
  assert.equal(h.run('savedRevision'), 1);
  assert.equal(h.run('editRevision'), 2);
  assert.equal(h.unloadBlocked(), true);
  await h.flush();
  assert.equal(h.requests.length, 2);
  h.succeed(h.requests[1]);
  await secondSave;
  assert.equal(h.element('saveState').textContent, 'Saved locally');
  assert.equal(h.unloadBlocked(), false);
});

test('article preview uses a byline paragraph and plain article body', () => {
  const h = harness();
  h.run(`project.articles = [{
    id:'a',
    title:'Plain text story',
    body:'First paragraph.\\n\\nSecond paragraph.',
    authors:[{name:'Alex Rivera',slug:'alex-rivera'}]
  }]; selectedId='a'; renderBodyPreview();`);
  assert.equal(h.run(`articleEditorSource(current())`),'<p class="byline">By <a href="https://sites.nova.edu/mako-media-network/author/alex-rivera/">Alex Rivera </a><span class="bybullet"> •</span></p>\n\nFirst paragraph.\n\nSecond paragraph.');
  h.run('openBodySource();');
  const source=h.element('bodySource');
  assert.match(source.value,/^<p class="byline">/);
  assert.match(source.value,/First paragraph\.\n\nSecond paragraph\.$/);
});

test('article body HTML is converted to plain text while byline stays HTML', () => {
  const h = harness();
  const result = h.run(`articleBodyPlainText({
    authors:[{name:'Antonio Miguel Escorzon',slug:''}],
    body:"Dear Readers,\\n\\nAntonio Miguel Escorzon\\n\\nTake care,\\n\\nAntonio Miguel Escorzon"
  })`);
  assert.match(result,/^Dear Readers,/);
  assert.doesNotMatch(result,/^<p>|<\/p>/);
  const source=h.run(`articleEditorSource({
    authors:[{name:'Antonio Miguel Escorzon',slug:''}],
    body:"Dear Readers,\\n\\nTake care,"
  })`);
  assert.match(source,/^<p class="byline">/);
  assert.match(source,/Dear Readers,\n\nTake care,$/);
});

test('failed autosave keeps a persistent failure message and dirty unload protection', async () => {
  const h = harness();
  h.run('queueSave()');
  const autosave = [...h.timers.values()][0]();
  await h.flush();
  h.requests[0].reject(new Error('Disk unavailable'));
  await autosave;
  assert.match(h.element('saveState').textContent, /Save failed/);
  assert.match(h.element('saveState').textContent, /changes remain in this tab/);
  assert.match(h.element('notice').textContent, /Could not save.*Disk unavailable/);
  assert.equal(h.element('notice').hidden, false);
  assert.equal(h.element('notice').attributes.role, 'alert');
  assert.equal(h.run('savedRevision'), 0);
  assert.equal(h.run('editRevision'), 1);
  assert.equal(h.unloadBlocked(), true);
  await h.flush();
  assert.match(h.element('saveState').textContent, /Save failed/);
});

test('each pending article has a status badge, no numeric prefix, and only the selected row is current', () => {
  const h = harness();
  h.run(`project.articles = [
    {id: 'a', title: 'Campus reporting', reviewed: false},
    {id: 'b', title: 'Arts coverage', reviewed: true},
    {id: 'c', title: '', reviewed: false},
    {id: 'd', title: 'Already drafted', wordpress_draft: {id: 10}},
    {id: 'e', title: 'Advertisement', kind: 'advertisement'}
  ]; selectedId = 'b'; renderList();`);
  const rows = h.element('articleList').children;
  assert.equal(rows.length, 3);
  for (const row of rows) {
    assert.match(row.html, /class="review-badge(?: is-reviewed)?"/);
    assert.doesNotMatch(row.html, /class="number"/);
    assert.doesNotMatch(row.textContent, /^\d+[.)\s]/);
  }
  assert.equal(rows[0].textContent, 'NEEDS REVIEW Campus reporting');
  assert.equal(rows[1].textContent, 'REVIEWED Arts coverage');
  assert.equal(rows[2].textContent, 'NEEDS REVIEW Untitled article');
  assert.deepEqual(rows.filter(row => row.attributes['aria-current'] === 'true').map(row => row.dataset.id), ['b']);
  assert.equal(rows[0].attributes['aria-current'], undefined);
  assert.equal(rows[2].attributes['aria-current'], undefined);
  h.run("selectedId = 'a'; renderList();");
  assert.deepEqual(h.element('articleList').children.filter(row => row.attributes['aria-current'] === 'true').map(row => row.dataset.id), ['a']);
});

test('queue search matches authors, combines with status, and preserves the open article', () => {
  const h = harness();
  h.run(`project.articles = [
    {id:'a', title:'Campus reporting', body:'A campus story.', authors:[{name:'Alex Rivera'}], reviewed:false},
    {id:'b', title:'Climate summit', body:'Another story.', authors:[{name:'Jordan Cole'}], reviewed:true},
    {id:'c', title:'Arts coverage', authors:[{name:'Jordan Cole'}], reviewed:false},
    {id:'d', title:'Drafted story', authors:[{name:'Jordan Cole'}], wordpress_draft:{id:10}}
  ]; selectedId='a'; renderList();`);
  h.element('queueSearch').value='  JORDAN  ';
  h.element('queueSearch').oninput();
  assert.deepEqual(h.element('articleList').children.map(row=>row.dataset.id),['b','c']);
  assert.equal(h.run('selectedId'),'a');
  assert.match(h.element('articlePosition').textContent,/outside this filter/);
  h.element('filterReviewed').onclick();
  assert.deepEqual(h.element('articleList').children.map(row=>row.dataset.id),['b']);
  assert.equal(h.element('filterReviewed').attributes['aria-pressed'],'true');
  assert.equal(h.element('queueAllCount').textContent,3);
  assert.equal(h.element('queueReviewedCount').textContent,1);
  h.element('queueSearch').value='No matching headline';
  h.element('queueSearch').oninput();
  assert.equal(h.element('articleList').children.length,0);
  assert.equal(h.element('queueEmpty').hidden,false);
  h.element('clearQueueFilters').onclick();
  assert.equal(h.element('articleList').children.length,3);
  assert.equal(h.element('queueEmpty').hidden,true);
  assert.equal(h.run('selectedId'),'a');
});
