const $=id=>document.getElementById(id);
const token=document.querySelector('meta[name="workbench-token"]').content;
let project=null,selectedId=null,saveTimer,saveQueue=Promise.resolve();
let draftPlan=null,drafting=false;
let editRevision=0,savedRevision=0,busyDepth=0;
let queueQuery='',queueFilter='all';
let wordpressSite='https://sites.nova.edu/mako-media-network';
let taxonomy={categories:[],tags:[]};
const current=()=>project?.articles.find(a=>a.id===selectedId);
const isArticle=a=>!a.kind||a.kind==='article';
const reviewArticles=()=>project?.articles.filter(a=>isArticle(a)&&!a.wordpress_draft)||[];
const visibleArticles=()=>reviewArticles().filter(article=>
    (queueFilter==='all'||(queueFilter==='reviewed'?!!article.reviewed:!article.reviewed))&&
    (!queueQuery||[article.title,...(article.authors||[]).map(author=>author.name)].join(' ').toLowerCase().includes(queueQuery)));
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const slug=s=>s.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
const allowedArticleTags=new Set(['P','BR','STRONG','B','EM','I','UL','OL','LI','BLOCKQUOTE','H2','H3','A','SPAN']);
function sanitizeArticleHtml(markup){
    const parsed=new DOMParser().parseFromString(`<div>${markup}</div>`,'text/html'),root=parsed.body.firstElementChild;
    const clean=node=>{
        for(const child of [...node.children]){
            if(['SCRIPT','STYLE','IFRAME','OBJECT','SVG','MATH'].includes(child.tagName)){child.remove();continue;}
            clean(child);
            if(!allowedArticleTags.has(child.tagName)){child.replaceWith(...child.childNodes);continue;}
            for(const attr of [...child.attributes]){
                const keep=(child.tagName==='P'&&attr.name==='class'&&attr.value==='byline')||
                    (child.tagName==='SPAN'&&attr.name==='class'&&attr.value==='bybullet')||
                    (child.tagName==='SPAN'&&attr.name==='class'&&attr.value==='byline-name')||
                    (child.tagName==='A'&&attr.name==='href'&&(/^(https?:|mailto:)/i.test(attr.value)||(attr.value.startsWith('/')&&!attr.value.startsWith('//'))));
                if(!keep)child.removeAttribute(attr.name);
            }
        }
    };
    clean(root);return root.innerHTML;
}
function plainBodyHtml(body){return String(body||'').trim().split(/\n\s*\n/).filter(Boolean).map(part=>`<p>${part.split('\n').map(esc).join('<br>')}</p>`).join('\n');}
function articleBodyHtml(article){return sanitizeArticleHtml(article.body_html||plainBodyHtml(article.body));}
function bylineHtml(article){
    const authors=(article.authors||[]).filter(person=>person.name?.trim());
    if(!authors.length)return '';
    const names=authors.map(person=>{
        if(!person.slug?.trim())return `<span class="byline-name">${esc(person.name.trim())} </span>`;
        const href=`${wordpressSite.replace(/\/$/,'')}/author/${encodeURIComponent((person.slug||'').trim())}/`;
        return `<a href="${esc(href)}">${esc(person.name.trim())} </a>`;
    });
    return `<p class="byline">By ${names.join('and ')}<span class="bybullet"> •</span></p>`;
}
function articleHtmlSource(article){return [bylineHtml(article),articleBodyHtml(article)].filter(Boolean).join('\n');}
function htmlText(node){
    if(node.nodeType===Node.TEXT_NODE)return node.nodeValue;
    if(node.nodeType!==Node.ELEMENT_NODE)return '';
    if(node.tagName==='BR')return '\n';
    const value=[...node.childNodes].map(htmlText).join('');
    return ['P','LI','BLOCKQUOTE','H2','H3'].includes(node.tagName)?`\n${value}\n`:value;
}
function commitBodySource(){
    const article=current();if(!article)return;
    const container=document.createElement('div');container.innerHTML=sanitizeArticleHtml($('bodySource').value);
    const byline=container.querySelector('.byline');
    article.authors=byline?[...byline.querySelectorAll('a,span.byline-name')].map(node=>{
        const href=node.getAttribute('href')||'';
        const match=href.match(/\/author\/([^/]+)\/?$/);
        let authorSlug='';try{authorSlug=match?decodeURIComponent(match[1]):'';}catch{}
        return {name:node.textContent.trim(),slug:authorSlug};
    }).filter(person=>person.name):[];
    byline?.remove();
    article.body_html=container.innerHTML.trim();
    article.body=[...container.childNodes].map(htmlText).join('').replace(/\n{3,}/g,'\n\n').trim();
    syncTags(article);changed();renderAuthors();
}
function openBodySource(){
    const source=$('bodySource');source.value=articleHtmlSource(current());
    source.hidden=false;$('bodyPreview').hidden=true;source.focus();source.setSelectionRange(0,0);
}
function renderBodyPreview(){
    const article=current();if(!article)return;
    $('bodyPreview').innerHTML=sanitizeArticleHtml(articleHtmlSource(article));
    $('bodyPreview').hidden=false;$('bodySource').hidden=true;
}
function notify(message,error=false){$('notice').textContent=message;$('notice').hidden=!message;$('notice').className=error?'error':'success';$('notice').setAttribute('role',error?'alert':'status');}
async function api(path,data){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Token':token},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'Request failed.');return result;}
async function busy(message,fn){
    const previousFocus=document.activeElement;
    const regions=[document.querySelector('header'),$('welcome'),$('workspace'),$('draftDialog')];
    $('busyText').textContent=message;
    if(!busyDepth++){regions.forEach(region=>region.inert=true);$('busy').hidden=false;$('busy').focus();}
    try{return await fn();}catch(e){notify(e.message,true);return null;}
    finally{if(!--busyDepth){$('busy').hidden=true;regions.forEach(region=>region.inert=false);if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});}}
}
function syncDefaultTags(a){a.tags??=[];if(a.default_tags_version!==1){if(!a.tags.some(t=>t.toLowerCase()==='add-about'))a.tags.push('add-about');a.default_tags_version=1;}const previous=a.default_author_names||[],names=[...new Set(a.authors.map(p=>p.name?.trim()).filter(Boolean))],old=new Set(previous.map(n=>n.toLowerCase())),now=new Set(names.map(n=>n.toLowerCase())),stale=new Set(previous.filter(n=>!now.has(n.toLowerCase())).map(n=>'posts by '+n.toLowerCase()));a.tags=a.tags.filter(t=>!stale.has(t.toLowerCase()));for(const name of names){const label='Posts By '+name;if(!old.has(name.toLowerCase())&&!a.tags.some(t=>t.toLowerCase()===label.toLowerCase()))a.tags.push(label);}a.default_author_names=names;}
function syncTags(a){syncDefaultTags(a);const old=new Set(a.generated_author_tags||[]);a.tags=(a.tags||[]).filter(t=>!old.has(t));a.generated_author_tags=a.auto_author_tags===false?[]:[...new Set(a.authors.filter(p=>p.name?.trim()).map(p=>'coauthor-'+slug(p.name)))];a.tags=[...new Set([...a.tags,...a.generated_author_tags])];if(a===current())$('tags').value=a.tags.join(', ');}
function changed(){if(!current())return;current().reviewed=false;$('reviewed').checked=false;queueSave();renderList();renderInspector();}
function queueSave(){editRevision++;clearTimeout(saveTimer);$('saveState').textContent='Unsaved changes';saveTimer=setTimeout(()=>saveNow().catch(e=>notify(`Could not save. ${e.message} Keep this tab open and try again.`,true)),650);}
async function saveNow(){
    clearTimeout(saveTimer);if(!project)return;
    for(const a of project.articles)syncTags(a);
    const snapshot=structuredClone(project),revision=editRevision;
    const request=saveQueue.catch(()=>{}).then(()=>api('/api/save',snapshot));saveQueue=request;
    try{await request;savedRevision=Math.max(savedRevision,revision);if(revision===editRevision)$('saveState').textContent='Saved locally';}
    catch(error){$('saveState').textContent='Save failed — changes remain in this tab';throw error;}
}
function renderList(){
  if(!project)return;
  const focusedId=$('articleList').contains(document.activeElement)?document.activeElement.dataset.id:null;
  const pending=reviewArticles();
  const count=pending.filter(a=>a.reviewed).length;
  $('batchDraft').disabled=!count;
  $('batchDraft').textContent=count?`Create reviewed drafts (${count})`:'Create reviewed drafts';
  const drafted=project.articles.filter(isArticle).length-pending.length;
  $('progress').textContent=`${pending.length} in review · ${drafted} drafted`;
  const visible=visibleArticles();
  $('queueAllCount').textContent=pending.length;
  $('queueNeedsCount').textContent=pending.length-count;
  $('queueReviewedCount').textContent=count;
  $('queueCount').textContent=queueQuery||queueFilter!=='all'?`${visible.length} of ${pending.length} articles`:`${pending.length} ${pending.length===1?'article':'articles'} in this queue`;
  $('queueEmpty').hidden=!!visible.length||!pending.length;
  $('articleList').innerHTML=visible.length?visible.map(a=>`
    <button data-id="${a.id}" class="${a.id===selectedId?'active':''}" ${a.id===selectedId?'aria-current="true"':''}>
      <span class="review-badge${a.reviewed?' is-reviewed':''}">${a.reviewed?'REVIEWED':'NEEDS REVIEW'}</span>
      <span class="article-title">${esc(a.title||'Untitled article')}</span>
      ${a.source_section?`<span class="article-context">${esc(a.source_section)}</span>`:''}
      ${a.body||(a.authors||[]).length?`<span class="article-row-meta"><span>${esc((a.authors||[]).map(author=>author.name).filter(Boolean).join(', ')||'No byline')}</span><span>${(a.body?.trim().split(/\s+/).filter(Boolean).length||0).toLocaleString()} words</span></span>`:''}
    </button>
  `).join(''):'';
  $('articleList').querySelectorAll('button').forEach(b=>b.onclick=()=>selectArticle(b.dataset.id));
  if(focusedId)Array.from($('articleList').querySelectorAll('button')).find(b=>b.dataset.id===focusedId)?.focus({preventScroll:true});
  updateArticleContext();
}
function updateArticleContext(){
    const article=current(),visible=visibleArticles(),position=visible.findIndex(item=>item.id===selectedId);
    $('articlePosition').textContent=!article?'No article selected':position<0?'Open article is outside this filter':`Article ${position+1} of ${visible.length}`;
    $('previousArticle').disabled=position<=0;
    $('nextArticle').disabled=!visible.length||position>=visible.length-1;
    $('articleStatus').textContent=article?.reviewed?'REVIEWED':'NEEDS REVIEW';
    $('articleStatus').className=`review-badge${article?.reviewed?' is-reviewed':''}`;
    const words=article?.body?.trim().split(/\s+/).filter(Boolean).length||0;
    $('wordCount').textContent=`${words.toLocaleString()} ${words===1?'word':'words'}`;
}
function selectArticle(id){selectedId=id;renderList();renderEditor();}
function setQueueFilter(filter){
    queueFilter=filter;
    for(const [id,value] of [['filterAll','all'],['filterNeeds','needs'],['filterReviewed','reviewed']])$(id).setAttribute('aria-pressed',String(filter===value));
    renderList();
}
function moveArticle(direction){
    const visible=visibleArticles(),position=visible.findIndex(article=>article.id===selectedId);
    const next=visible[position+direction];
    if(next){selectArticle(next.id);Array.from($('articleList').querySelectorAll('button')).find(button=>button.dataset.id===next.id)?.scrollIntoView({block:'nearest'});}
}
$('queueSearch').oninput=()=>{queueQuery=$('queueSearch').value.trim().toLowerCase();renderList();};
$('filterAll').onclick=()=>setQueueFilter('all');
$('filterNeeds').onclick=()=>setQueueFilter('needs');
$('filterReviewed').onclick=()=>setQueueFilter('reviewed');
$('clearQueueFilters').onclick=()=>{queueQuery='';$('queueSearch').value='';setQueueFilter('all');$('queueSearch').focus();};
$('previousArticle').onclick=()=>moveArticle(-1);
$('nextArticle').onclick=()=>moveArticle(1);
function renderEditor(){const a=current();$('importReview').hidden=!(a?.source==='INDD'&&!a.source_bytes_verified);$('editorForm').hidden=!a;$('emptyQueue').hidden=!!a;if(!a)return;$('categorySource').hidden=!a.source_section;$('categorySource').textContent=`InDesign section · ${a.source_section||''}`;$('title').value=a.title;renderBodyPreview();$('categories').value=a.categories.join(', ');$('tags').value=a.tags.join(', ');$('reviewed').checked=!!a.reviewed;$('autoTags').checked=a.auto_author_tags!==false;renderAuthors();renderInspector();}
function renderAuthors(){
    const article=current();
    article.authors??=[];
    $('authors').innerHTML=article.authors.map((person,index)=>`<div class="author-entry"><div class="author-row"><label class="byline-field">Author name<input aria-label="Author ${index+1} name" data-author-name="${index}" value="${esc(person.name||'')}" placeholder="Full name"></label><label class="byline-field">Author slug<input aria-label="Author ${index+1} slug" data-author-slug="${index}" value="${esc(person.slug||'')}" placeholder="wordpress-author-slug"></label><button type="button" class="text-button" data-remove="${index}" aria-label="Remove author ${index+1}">Remove</button></div></div>`).join('');
    $('authors').querySelectorAll('[data-author-name],[data-author-slug]').forEach(input=>input.oninput=()=>{
        const index=Number(input.dataset.authorName??input.dataset.authorSlug);
        article.authors[index]??={name:'',slug:''};
        if(input.hasAttribute('data-author-name'))article.authors[index].name=input.value;
        else article.authors[index].slug=input.value;
        syncTags(article);changed();renderBodyPreview();
    });
    $('authors').querySelectorAll('[data-remove]').forEach(button=>button.onclick=()=>{
        article.authors.splice(Number(button.dataset.remove),1);syncTags(article);changed();renderAuthors();renderBodyPreview();
    });
}
$('addAuthor').onclick=()=>{
    if(!current())return;
    current().authors.push({name:'',slug:''});changed();renderAuthors();
    $('authors').querySelectorAll('[data-author-name]').item(current().authors.length-1)?.focus();
};
async function mount(){
    editRevision=0;savedRevision=0;
    queueQuery='';queueFilter='all';$('queueSearch').value='';
    for(const id of ['filterAll','filterNeeds','filterReviewed'])$(id).setAttribute('aria-pressed',String(id==='filterAll'));
    $('welcome').hidden=true;
    $('workspace').hidden=false;
    $('closeIssue').hidden=false;
    $('issueName').textContent=project.name;
    $('saveState').textContent='Saved locally';
    selectedId=reviewArticles()[0]?.id||null;
    for(const article of project.articles){
        article.authors??=[];
        article.categories??=[];
        article.tags??=[];
        syncTags(article);
    }
    renderList();
    renderEditor();
    notify('');
    const response=await fetch('/api/wordpress');
    const settings=await response.json();
    if(!response.ok)throw Error(settings.error);
    wordpressSite=settings.site||wordpressSite;renderBodyPreview();
    if(!settings.configured||!reviewArticles().length)return;
    try { const response=await fetch('/api/taxonomy'); const terms=await response.json(); if(response.ok)taxonomy=terms; else notify(terms.error,true); } catch(error){notify(error.message,true);}
    renderInspector();
    $('busyText').textContent='Checking categories in WordPress…';
    const prepared=await api('/api/prepare-issue',{id:project.id});
    project=prepared.project;
    renderList();
    renderEditor();
    const message=prepared.suggested?`${prepared.suggested} categories suggested`:'';
    notify([message,prepared.warning].filter(Boolean).join('. '),!!prepared.warning);
}
async function upload(file){if(!file)return;await busy('Verifying INDD and recovering the full issue…',async()=>{const response=await fetch('/api/indd',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(file.name),'X-Workbench-Token':token},body:file});const result=await response.json();if(!response.ok)throw Error(result.error);project=result;await mount();});}
for(const [id,key] of [['title','title']])$(id).oninput=()=>{if(current()){current()[key]=$(id).value;changed();}};
$('bodyPreview').onclick=openBodySource;
$('bodyPreview').onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openBodySource();}};
$('bodySource').oninput=commitBodySource;
$('bodySource').onblur=()=>{commitBodySource();renderBodyPreview();};
for(const [id,key] of [['categories','categories'],['tags','tags']])$(id).oninput=()=>{if(current()){current()[key]=$(id).value.split(',').map(s=>s.trim()).filter(Boolean);if(key==='categories')current().categories_edited=true;changed();}};
$('reviewed').onchange=()=>{if(current()){current().reviewed=$('reviewed').checked;queueSave();renderList();renderInspector();}};
$('autoTags').onchange=()=>{if(current()){current().auto_author_tags=$('autoTags').checked;syncTags(current());changed();}};
$('upload').onchange=event=>{
    const file=event.target.files[0];
    event.target.value='';
    upload(file);
};
$('closeIssue').onclick=async()=>{
    if(!project)return;
    await busy('Saving and closing the INDD…',async()=>{
        await saveNow();
        await api('/api/close',{id:project.id});
        project=null;
        selectedId=null;
        $('issueName').textContent='';
        $('workspace').hidden=true;
        $('closeIssue').hidden=true;
        $('welcome').hidden=false;
        notify('');
    });
};
$('newArticle').onclick=()=>busy('Adding an article…',async()=>{const a=await api('/api/new',{});project.articles.push(a);queueSave();await saveNow();queueQuery='';$('queueSearch').value='';setQueueFilter('all');selectArticle(a.id);});
$('removeArticle').onclick=async()=>{
    const article=current();if(!article||!confirm('Remove this article and all edits from the local issue? This cannot be undone here. The original INDD is kept.'))return;
    await busy('Removing article…',async()=>{
        const originalArticles=project.articles;
        project.articles=project.articles.filter(item=>item.id!==article.id);queueSave();
        try{await saveNow();selectedId=reviewArticles()[0]?.id||null;renderList();renderEditor();}
        catch(error){project.articles=originalArticles;queueSave();renderList();renderEditor();throw error;}
    });
};
async function openDraftCheck(articles,mode){
    if(!articles.length)return;
    const checked=await busy('Checking articles in WordPress…',async()=>{
        await saveNow();
        return api('/api/preflight',{
            id:project.id,
            article_ids:articles.map(article=>article.id),
            require_reviewed:mode!=='check'
        });
    });
    if(!checked)return;
    draftPlan={...checked,mode,issueId:project.id};
    $('draftHeading').textContent=mode==='check'?'Article check':mode==='batch'?'Create reviewed drafts?':'Create this draft?';
    $('draftChecks').dataset.mode=mode;
    $('draftSummary').textContent=`WordPress site · ${checked.site}`;
    $('draftChecks').innerHTML=`<ul class="draft-checks">${checked.checks.map(check=>{
        const errors=check.errors.map(error=>`<li>${esc(error)}</li>`);
        const duplicates=check.duplicates.map(match=>
            `<li>Possible duplicate · <a href="${esc(match.url)}" target="_blank" rel="noopener">WordPress #${match.id} (${esc(match.status)})</a></li>`);
        const issues=[...errors,...duplicates];
        const actions=issues.length?`<span class="check-fixes">${check.errors.some(error=>/byline/i.test(error))?'<button type="button" data-fix="byline">Fix byline</button>':''}${check.errors.some(error=>/category/i.test(error))?'<button type="button" data-fix="categories">Fix categories</button>':''}${check.errors.some(error=>/tag/i.test(error))?'<button type="button" data-fix="tags">Fix tags</button>':''}</span>`:'';
        return `<li data-article-id="${esc(check.id)}"><strong>${esc(check.title)}</strong>${issues.length?`<ul>${issues.join('')}</ul>${actions}`:'<span class="help"> · Ready</span>'}</li>`;
    }).join('')}</ul>`;
    $('draftResult').textContent='';
    $('includeDuplicate').checked=false;
    $('duplicateOption').hidden=mode!=='single'||!!checked.checks[0].errors.length||!checked.checks[0].duplicates.length;
    $('draftChecks').querySelectorAll('[data-fix]').forEach(button=>button.onclick=()=>{
        $('draftDialog').close();
        selectArticle(button.closest('[data-article-id]').dataset.articleId);
        const target=button.dataset.fix==='byline'?'byline':button.dataset.fix;
        const control=target==='byline'?$('authors').querySelector('[data-author-name]'):$((target==='categories'?'categories':'tags'));
        const details=control?.closest('details');if(details)details.open=true;
        control?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});
        control?.focus({preventScroll:true});
        notify(`Review ${target} for “${current().title||'Untitled article'}”, then check the article again.`,true);
    });
    updateDraftButton();
    $('draftDialog').showModal();
}
function readyDrafts(){
    if(!draftPlan||draftPlan.mode==='check')return [];
    return draftPlan.checks.filter(check=>!check.errors.length&&
        (!check.duplicates.length||(draftPlan.mode==='single'&&$('includeDuplicate').checked)));
}
function updateDraftButton(){
    const count=readyDrafts().length;
    $('confirmDraft').hidden=!count;
    $('confirmDraft').disabled=drafting;
    $('confirmDraft').textContent=count===1?'Create 1 WordPress draft':`Create ${count} WordPress drafts`;
}
$('includeDuplicate').onchange=updateDraftButton;
$('checkArticle').onclick=()=>openDraftCheck(current()?[current()]:[],'check');
$('draftBtn').onclick=()=>{
    const article=current();
    if(!article)return;
    if(!article.reviewed)return notify('Check the article, then mark it reviewed before creating a draft.',true);
    openDraftCheck([article],'single');
};
$('batchDraft').onclick=()=>openDraftCheck(reviewArticles().filter(a=>a.reviewed),'batch');
$('draftDialog').addEventListener('cancel',event=>{if(drafting)event.preventDefault();});
$('confirmDraft').onclick=async()=>{
    const ready=readyDrafts();
    if(drafting||!ready.length)return;
    drafting=true;
    $('closeDraftDialog').disabled=true;
    $('includeDuplicate').disabled=true;
    updateDraftButton();
    const position=reviewArticles().findIndex(a=>a.id===selectedId);
    const readyIds=new Set(ready.map(check=>check.id));
    const results=[];
    let created=0;
    try{
        for(const check of ready){
            $('draftResult').textContent=`Creating draft ${results.length+1} of ${ready.length}…`;
            try{
                const result=await api('/api/draft',{
                    id:draftPlan.issueId,article_id:check.id,site:draftPlan.site,signature:check.signature,
                    acknowledged_duplicates:check.duplicates.map(match=>match.id).sort((a,b)=>a-b)
                });
                project=result.project;
                created++;
                results.push(`<li>${esc(check.title)} · <a href="${esc(result.edit_url)}" target="_blank" rel="noopener">Open draft #${result.id}</a></li>`);
            }catch(error){
                results.push(`<li>${esc(check.title)} · ${esc(error.message)}</li>`);
            }
        }
        const pending=reviewArticles();
        if(!pending.some(a=>a.id===selectedId)){
            selectedId=pending[Math.max(0,Math.min(position,pending.length-1))]?.id||null;
        }
        renderList();
        renderEditor();
        const skipped=draftPlan.checks.filter(check=>!readyIds.has(check.id)).length;
        const remaining=skipped+ready.length-created;
        $('draftResult').innerHTML=`<p>${created} created · ${remaining} still in review from this selection</p><ul>${results.join('')}</ul>`;
    }finally{
        drafting=false;
        $('closeDraftDialog').disabled=false;
        $('includeDuplicate').disabled=false;
        $('duplicateOption').hidden=true;
        $('confirmDraft').hidden=true;
    }
};
window.addEventListener('beforeunload',e=>{if(editRevision!==savedRevision){e.preventDefault();e.returnValue='';}});
async function init(){
    await busy('Opening WordPress Drafts…',async()=>{
        const response=await fetch('/api/issue');
        const issue=await response.json();
        if(!response.ok)throw Error(issue.error||'Could not open the INDD.');
        project=issue.project;
        if(project)await mount();
        else $('welcome').hidden=false;
    });
}

function renderInspector(){
 const a=current();if(!a)return;
 const names=(a.authors||[]).map(p=>p.name).filter(Boolean);
 $('authorDisplay').textContent=names.join(', ')||'No author assigned';
 $('authorAvatar').textContent=names[0]?.split(/\s+/).map(s=>s[0]).slice(0,2).join('')||'—';
 const categories=[...new Set([...taxonomy.categories.map(t=>t.name),...a.categories])];
 $('categoryPills').innerHTML=categories.map(name=>'<button type="button" aria-pressed="'+a.categories.includes(name)+'" data-category="'+esc(name)+'">'+esc(name)+'</button>').join('');
 $('categoryPills').querySelectorAll('button').forEach(b=>b.onclick=()=>{const name=b.dataset.category;a.categories=a.categories.includes(name)?a.categories.filter(n=>n!==name):[...a.categories,name];a.categories_edited=true;$('categories').value=a.categories.join(', ');changed();});
 $('tagChips').innerHTML=a.tags.map((name,i)=>'<span class="tag-chip">'+esc(name)+'<button type="button" aria-label="Remove '+esc(name)+'" data-tag="'+i+'">×</button></span>').join('');
 $('tagChips').querySelectorAll('button').forEach(b=>b.onclick=()=>{const name=a.tags[Number(b.dataset.tag)];if((a.generated_author_tags||[]).includes(name)){a.auto_author_tags=false;$('autoTags').checked=false;a.generated_author_tags=[];}a.tags=a.tags.filter(t=>t!==name);$('tags').value=a.tags.join(', ');changed();});
 const text=(a.title+' '+a.body).toLowerCase();
 const suggestions=taxonomy.tags.filter(t=>!a.tags.includes(t.name)&&text.includes(t.name.toLowerCase())).slice(0,6);
 $('tagSuggestions').innerHTML=suggestions.map(t=>'<button data-suggest="'+esc(t.name)+'">+ '+esc(t.name)+'</button>').join('')||'<span class="help">No matching existing tags.</span>';
 $('tagSuggestions').querySelectorAll('button').forEach(b=>b.onclick=()=>{a.tags.push(b.dataset.suggest);$('tags').value=a.tags.join(', ');changed();});
 $('slugField').value=a.slug||slug(a.title);
 $('draftBtn').disabled=!a.reviewed;
}
$('tagEntry').onkeydown=event=>{if(event.key!=='Enter'||!current())return;event.preventDefault();const value=$('tagEntry').value.trim();if(value&&!current().tags.includes(value)){current().tags.push(value);$('tags').value=current().tags.join(', ');changed();}$('tagEntry').value='';};
$('slugField').oninput=()=>{if(current()){current().slug=$('slugField').value;changed();}};

init();
