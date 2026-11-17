// Isolated headless app tests. All API data is synthetic and every write is mocked.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const output = path.join(__dirname, '..', 'artifacts', 'review');
const paragraph = 'The campus community gathered this week to discuss the next chapter of student life. Students and faculty shared their ideas, asked questions, and outlined the work still ahead. The conversation will continue at the next open meeting.';
function fixture() {
  return { id: 'a'.repeat(32), name: 'The Current · Vol. 37, Issue 4 · October 29, 2026', articles: [
    ['Campus reporting begins with a conversation', 'Campus Life', false],
    ['Students prepare for the regional climate summit', '', true],
    ['A new chapter for the student arts community', 'Arts & Culture', true],
    ['Wellness Week brings the campus together', 'Campus Life', false],
    ['Building a more connected university', 'News', false],
    ['Sharks speak: what would you change on campus?', 'Opinions', false],
    ['A season to remember', 'Sports', false]
  ].map(([title, section, reviewed], i) => ({ id: String(i + 1), title, body: [paragraph, paragraph, paragraph].join('\n\n'), authors: [{name: i === 1 ? 'Jordan Cole' : 'Alex Rivera', handle: '', url: '', byline_only: true}], categories: section ? [section] : [], tags: ['add-about'], source: 'INDD', source_section: section, reviewed, auto_author_tags: false, default_tags_version: 1 })) };
}
async function open(browser, viewport, project = fixture()) {
  const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = [];
  const calls = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    const data = request.method() === 'POST' ? request.postDataJSON() : {};
    calls.push(pathname);
    let result;
    if (pathname === '/api/issue') result = { project };
    else if (pathname === '/api/wordpress') result = { configured: false, site: 'https://example.org/news' };
    else if (pathname === '/api/save') { project = data; result = {ok: true}; }
    else if (pathname === '/api/preflight') result = { site: 'https://example.org/news', checks: data.article_ids.map(id => {
      const article = project.articles.find(a => a.id === id);
      return { id, title: article.title, errors: article.categories.length ? [] : ['Choose an existing WordPress category.'], duplicates: [], signature: 'test-signature' };
    }) };
    else if (pathname === '/api/draft') {
      const article = project.articles.find(a => a.id === data.article_id);
      article.wordpress_draft = {id: 123};
      result = { project, id: 123, edit_url: 'https://example.org/wp-admin/post.php?post=123' };
    } else if (pathname === '/api/close') { project = null; result = {ok:true}; }
    else if (pathname === '/api/author') result = { authors: [] };
    else throw new Error('Unexpected API call: ' + pathname);
    await route.fulfill({json: result});
  });
  await page.route('http://workbench.test/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.startsWith('/api/')) return route.fallback();
    const filename = pathname === '/' ? 'index.html' : pathname.slice(1);
    const file = await fs.readFile(path.join(__dirname, '..', filename));
    const contentType = filename.endsWith('.html') ? 'text/html' : filename.endsWith('.css') ? 'text/css' : filename.endsWith('.ttf') ? 'font/ttf' : 'text/javascript';
    await route.fulfill({body:file, contentType});
  });
  await page.goto('http://workbench.test/');
  await page.locator('#busy').waitFor({state:'hidden'});
  await page.evaluate(() => document.fonts.ready);
  return {page, context, errors, calls};
}
async function noOverflow(page) {
  const result = await page.evaluate(() => ({width:innerWidth, scroll:document.documentElement.scrollWidth, bad:[...document.querySelectorAll('input,textarea,button,nav,section')].filter(e => e.getClientRects().length && e.getBoundingClientRect().right > innerWidth + 2).map(e=>e.id||e.className)}));
  assert.ok(result.scroll <= result.width + 1, JSON.stringify(result));
  assert.deepEqual(result.bad, [], JSON.stringify(result));
}
(async () => {
  await fs.mkdir(output, {recursive:true});
  const browser = await chromium.launch({headless:true, channel:process.env.PLAYWRIGHT_CHANNEL || 'msedge'});
  try {
    for (const [name, width, height] of [['desktop',1440,1000],['user-1280',1280,900],['tablet',900,1000],['mobile',390,844],['narrow',320,800]]) {
      const {page,context,errors,calls} = await open(browser,{width,height});
      await noOverflow(page);
      assert.equal(await page.locator('#articleList button').count(),7);
      await page.screenshot({path:path.join(output,name+'.png'),fullPage:true});
      if (name === 'desktop') {
        assert.match(await page.locator('#articleList button').first().innerText(), /Alex Rivera[\s\S]*111 words/);
        await page.locator('#bodyPreview').click();
        await page.locator('#bodySource').fill('<p>Edited article text.</p>');
        await page.locator('#bodySource').blur();
        await page.waitForFunction(()=>document.getElementById('saveState').textContent==='Saved locally');
        assert.match(await page.locator('#articleList button').first().innerText(), /3 words/);
        await page.locator('#filterReviewed').click();
        assert.equal(await page.locator('#articleList button').count(),2);
        await page.screenshot({path:path.join(output,'reviewed-filter.png'),fullPage:true});
        await page.locator('#filterAll').click();
        await page.locator('#queueSearch').fill('Jordan');
        assert.equal(await page.locator('#articleList button').count(),1);
        await page.locator('#articleList button').click();
        assert.match(await page.locator('#title').inputValue(), /climate summit/);
        await page.locator('#queueSearch').fill('no matching story');
        assert.equal(await page.locator('#queueEmpty').isVisible(),true);
        await page.locator('#clearQueueFilters').click();
        await page.locator('#articleList button').first().click();
        await page.locator('#articleList button').nth(1).click();
        await page.locator('#draftBtn').click();
        await page.locator('#draftDialog').waitFor({state:'visible'});
        assert.equal(calls.filter(call=>call==='/api/draft').length,0);
        await page.screenshot({path:path.join(output,'draft-check.png'),fullPage:true});
        await page.locator('[data-fix="categories"]').click();
        assert.match(await page.locator('#title').inputValue(),/climate summit/);
        assert.equal(await page.locator('#categories').evaluate(e=>e===document.activeElement),true);
        await page.locator('#categories').fill('News');
        await page.waitForFunction(()=>document.getElementById('saveState').textContent==='Saved locally');
        await page.locator('#reviewed').check();
        await page.locator('#draftBtn').click();
        await page.locator('#draftDialog').waitFor({state:'visible'});
        await page.locator('#confirmDraft').click();
        await page.waitForFunction(()=>document.getElementById('draftResult').textContent.includes('1 created'));
        assert.equal(calls.filter(call=>call==='/api/draft').length,1);
        await page.locator('#closeDraftDialog').click();
        assert.equal(await page.locator('#articleList button').count(),6);
        const currentTitle=await page.locator('#title').inputValue();
        await page.locator('#nextArticle').click();
        assert.notEqual(await page.locator('#title').inputValue(),currentTitle);
        await page.locator('#previousArticle').click();
        assert.equal(await page.locator('#title').inputValue(),currentTitle);
        await page.locator('#closeIssue').click();
        await page.locator('#welcome').waitFor({state:'visible'});
        assert.equal(await page.locator('#issueName').innerText(),'');
      }
      assert.deepEqual(errors,[]);
      await context.close();
      console.log('PASS',name,width+'x'+height);
    }
    for (const [name,width,height] of [['welcome-desktop',1440,1000],['welcome-mobile',390,844]]) {
      const {page,context,errors} = await open(browser,{width,height},null);
      await page.locator('#welcome').waitFor({state:'visible'});
      await noOverflow(page);
      await page.screenshot({path:path.join(output,name+'.png'),fullPage:true});
      assert.deepEqual(errors,[]);
      await context.close();
      console.log('PASS',name);
    }
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
