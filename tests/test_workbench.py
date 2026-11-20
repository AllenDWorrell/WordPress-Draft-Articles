import copy,hashlib,io,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from indd_reader import Box,Story,group_articles,SIGNATURE
from xml.etree import ElementTree

ROOT=Path(__file__).resolve().parents[1]

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.old=app.DATA;app.DATA=Path(self.temp.name)
        self.sid='a'*32;(app.DATA/self.sid).mkdir()
        self.a=app.article('Test article','Allen Worrell');self.a['body']='One paragraph.\n\nAnother paragraph.'
        self.a['tags']=[]
        self.a['source_body']='Original source';self.p=dict(id=self.sid,articles=[self.a],source_hash='abc')
        self.c=dict(site='https://example.org/news',username='editor',password='applicationpassword')
        app.save(self.p)
    def tearDown(self):
        app._REPOSITORY=None
        app._REPOSITORY_ROOT=None
        app.DATA=self.old
        assert Path(self.temp.name).resolve().is_relative_to(Path(__file__).resolve().parent)
        self.temp.cleanup()

    def test_windows_keyring_credentials_are_stored_and_removed(self):
        secrets={}
        class FakeKeyring:
            def set_password(self,service,key,value):secrets[(service,key)]=value
            def get_password(self,service,key):return secrets.get((service,key))
            def delete_password(self,service,key):
                if (service,key) in secrets:
                    del secrets[(service,key)]
        fake=FakeKeyring()
        import wordpress
        with patch.object(wordpress,'keyring',fake):
            wordpress.save_credentials('https://example.org','local-editor','abcd efgh')
            status=wordpress.credential_status()
            credentials=wordpress.get_credentials('https://example.org')
            self.assertTrue(status['configured'])
            self.assertEqual(credentials['username'],'local-editor')
            self.assertEqual(credentials['password'],'abcd efgh')
            wordpress.delete_credentials()
            self.assertFalse(wordpress.credential_status()['configured'])
    def test_duplicate_import_job_is_reused_and_cancelled(self):
        raw=b'import-data'
        app.IMPORT_JOBS.clear()
        with patch.object(app,'import_indd',side_effect=lambda raw,name:(__import__('time').sleep(.1),dict(id='a'*32))[1]):
            first=app.start_import_job(raw,'Issue.indd')
            second=app.start_import_job(raw,'Issue.indd')
            self.assertEqual(first,second)
            result=app.cancel_import_job(first)
        self.assertEqual(result['state'],'cancelled')

    def test_author_prefix_queries_wordpress_and_keeps_account_slug(self):
        user = dict(id=182, name='Allen Worrell', username='aw2362', slug='allen-worrell',
                    link='https://example.org/news/author/allen-worrell/')
        with patch.object(app, 'wp_request', return_value=[user]) as request:
            author, = app.search_wordpress_authors('aw', self.c)
        self.assertIn('search=aw', request.call_args.args[1])
        self.assertIn('context=edit', request.call_args.args[1])
        self.assertEqual(author['handle'], 'aw2362')
        self.assertEqual(author['wp_slug'], 'allen-worrell')
        self.assertEqual(author['url'], user['link'])
        self.assertEqual(author['wp_user_id'], 182)
    def test_default_tags_follow_author_names(self):
        a=app.article('New article','Allen Worrell')
        self.assertEqual(a['tags'],['add-about','Posts By Allen Worrell'])
        a['authors'].append(dict(name='Mora Sampaio'))
        app.apply_default_tags(a)
        self.assertIn('Posts By Mora Sampaio',a['tags'])
        self.assertNotIn('posts-by',a['tags'])
    def test_existing_entries_get_defaults_once_and_removals_persist(self):
        self.a.pop('default_tags_version');self.a.pop('default_author_names')
        self.a['tags']=['custom-tag'];app.save(self.p)
        loaded=app.load(self.sid)
        self.assertEqual(loaded['articles'][0]['tags'],['custom-tag','add-about','Posts By Allen Worrell'])
        loaded['articles'][0]['tags']=['custom-tag']
        app.save_edits(loaded)
        self.assertEqual(app.load(self.sid)['articles'][0]['tags'],['custom-tag'])
        loaded=app.load(self.sid);loaded['articles'][0]['authors']=[dict(name='Jonathan Paul')]
        app.save_edits(loaded)
        tags=app.load(self.sid)['articles'][0]['tags']
        self.assertEqual(tags,['custom-tag','Posts By Jonathan Paul'])
    def test_author_search_falls_back_and_returns_all_matches(self):
        users = [dict(id=1, name='Allen Worrell', slug='aw2362'), dict(id=2, name='Other Person', slug='aw1234')]
        with patch.object(app, 'wp_request', side_effect=[app.WordPressError(403, 'Restricted'), users]) as request:
            matches = app.search_wordpress_authors('aw', self.c)
        self.assertEqual([a['handle'] for a in matches], ['aw2362', 'aw1234'])
        self.assertIn('who=authors', request.call_args.args[1])
        self.assertFalse((app.DATA / 'authors.json').exists())

    def test_draft_uses_selected_wordpress_author_id(self):
        self.a['reviewed'] = True
        self.a['authors'][0].update(handle='aw2362', wp_user_id=182, wp_site=self.c['site'])
        with patch.object(app, 'wp_request', return_value=dict(id=90, status='draft')) as request:
            app.create_draft(self.p, self.a['id'], self.c)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[1], 'posts')
        self.assertEqual(request.call_args.args[4]['author'], 182)
    def test_plain_byline_and_paragraphs(self):
        self.a['authors']=[dict(name='Mora Sampaio',url=app.DEFAULT_SITE+'/author/ms6195/'),dict(name='Cynthia Maloney',url=app.DEFAULT_SITE+'/author/cm4259/')]
        self.a['body']='Arts & science — “a quote.”\n\nA second paragraph.'
        text=app.post_text(self.a)
        self.assertEqual(text,'By Mora Sampaio and Cynthia Maloney\n\nArts & science — “a quote.”\n\nA second paragraph.')
        self.assertNotIn('<p',text);self.assertNotIn('<a',text);self.assertNotIn('<span',text)
    def test_source_is_immutable_on_save(self):
        edited=copy.deepcopy(self.p);edited['articles'][0].update(body='Edited body',source_body='Tampered',source_parts=['bad'],auto_author_tags=False)
        result=app.save_edits(edited)
        self.assertEqual(result['articles'][0]['body'],'Edited body')
        self.assertEqual(result['articles'][0]['source_body'],'Original source')
        self.assertEqual(result['articles'][0]['source_parts'],[])
        self.assertFalse(result['articles'][0]['auto_author_tags'])
    def test_unreviewed_draft_is_blocked(self):
        with patch.object(app,'wp_request') as request:
            with self.assertRaisesRegex(ValueError,'Review'):app.create_draft(self.p,self.a['id'],self.c)
            request.assert_not_called()
    def test_draft_only_with_verified_user(self):
        self.a['reviewed']=True;self.a['authors'][0].update(handle='aw2362',url=app.DEFAULT_SITE+'/author/aw2362/')
        calls=[]
        def fake(base,path,user,password,payload=None):
            calls.append((path,payload))
            if path.startswith('users?slug='):return [dict(id=182,slug='aw2362')]
            return dict(id=90,status='draft')
        with patch.object(app,'wp_request',side_effect=fake):app.create_draft(self.p,self.a['id'],self.c)
        payload=calls[-1][1]
        self.assertEqual(payload['status'],'draft');self.assertEqual(payload['author'],182)
        self.assertNotIn('featured_media',payload);self.assertNotIn('<img',payload['content'])
        self.assertEqual(payload['content'],'By Allen Worrell\n\nOne paragraph.\n\nAnother paragraph.')
    def test_primary_account_not_found_blocks_post(self):
        self.a['reviewed']=True;self.a['authors'][0]['handle']='aw2362'
        with patch.object(app,'wp_request',return_value=[]) as request:
            with self.assertRaisesRegex(ValueError,'could not be verified'):app.create_draft(self.p,self.a['id'],self.c)
            self.assertEqual(request.call_count,1)
    def test_duplicates_across_reimport_are_blocked(self):
        self.a.update(reviewed=True,native_key='1')
        with patch.object(app,'wp_request',return_value=dict(id=55,status='draft')) as request:
            app.create_draft(self.p,self.a['id'],self.c)
            self.a['id']='b'*32
            with self.assertRaisesRegex(ValueError,'already sent'):app.create_draft(self.p,self.a['id'],self.c)
            self.assertEqual(request.call_count,1)
    def test_timeout_is_not_retried(self):
        self.a['reviewed']=True
        with patch.object(app,'wp_request',side_effect=TimeoutError('timeout')) as request:
            with self.assertRaises(TimeoutError):app.create_draft(self.p,self.a['id'],self.c)
            with self.assertRaisesRegex(ValueError,'unresolved'):app.create_draft(self.p,self.a['id'],self.c)
            self.assertEqual(request.call_count,1)
    def test_confirmed_draft_leaves_review_and_survives_stale_save(self):
        self.a.update(reviewed=True,native_key='1')
        second=app.article('Next article');self.p['articles'].append(second)
        app.save(self.p);stale=copy.deepcopy(self.p)
        with patch.object(app,'wp_request',return_value=dict(id=90,status='draft')):
            result=app.create_draft(self.p,self.a['id'],self.c)
        self.assertEqual(result['project']['articles'][0]['wordpress_draft']['id'],90)
        self.assertEqual(len(result['project']['articles']),2)
        self.assertEqual(result['project']['articles'][0]['body'],self.a['body'])
        app.save_edits(stale)
        reloaded=app.load(self.sid)
        remaining=[a['title'] for a in reloaded['articles'] if not a.get('wordpress_draft')]
        self.assertEqual(remaining,['Next article'])
    def test_unconfirmed_response_stays_in_review(self):
        self.a['reviewed']=True;app.save(self.p)
        with patch.object(app,'wp_request',return_value=dict(id=77,status='pending')):
            with self.assertRaisesRegex(ValueError,'did not confirm draft'):app.create_draft(self.p,self.a['id'],self.c)
        self.assertNotIn('wordpress_draft',app.load(self.sid)['articles'][0])

    def test_reconcile_unresolved_draft_requires_exactly_one_match(self):
        self.a.update(reviewed=True,native_key='1')
        key=app.draft_key(self.c['site'],self.p,'1')
        app.repository().set_draft(key,dict(state='unresolved',status='unknown',
                                           source_hash='abc',native_key='1',title=self.a['title']))
        with patch.object(app,'wp_read',return_value=[
            dict(id=81,title={'raw':self.a['title']},status='draft')
        ]):
            record=app.reconcile_draft(self.p,self.a['id'],self.c)
        self.assertEqual(record['state'],'confirmed')
        self.assertEqual(record['id'],81)
        self.assertEqual(app.load(self.sid)['articles'][0]['wordpress_draft']['id'],81)
    def test_existing_draft_ids_backfill_but_pending_attempts_do_not(self):
        key=app.draft_key(app.DEFAULT_SITE,self.p,self.a['id'])
        path=app.DATA/'wordpress-drafts.json'
        path.write_text(json.dumps({key:'attempt pending'}),'utf8')
        self.assertNotIn('wordpress_draft',app.load(self.sid)['articles'][0])
        path.write_text(json.dumps({key:123}),'utf8')
        self.assertEqual(app.load(self.sid)['articles'][0]['wordpress_draft']['id'],123)
    def test_unknown_terms_do_not_create_post(self):
        self.a.update(reviewed=True,categories=['Unknown'])
        with patch.object(app,'wp_request',return_value=[]) as request:
            with self.assertRaisesRegex(ValueError,'existing categor'):app.create_draft(self.p,self.a['id'],self.c)
            self.assertEqual(request.call_count,1)
    def test_indd_opens_for_review(self):
        raw = SIGNATURE + b'another INDD'
        app.set_active_issue(None)
        recovered = [dict(title='A different issue', authors=['Allen Worrell'], kind='article',
                          body='Body text for review.', native_key='story:u123', source_parts=[])]
        with patch.object(app, 'read_indd', return_value=recovered) as read:
            project = app.import_indd(raw, 'Different Issue.indd')
        read.assert_called_once_with(raw, ROOT / 'tools' / 'indd.exe')
        self.assertEqual(project['name'], 'Different Issue')
        self.assertEqual(app.active_issue_id(), project['id'])
        article = project['articles'][0]
        self.assertEqual(article['body'], 'Body text for review.')
        self.assertEqual(article['authors'][0]['name'], 'Allen Worrell')
        self.assertEqual(article['authors'][0]['handle'], '')
        self.assertFalse(article['reviewed'])

    def test_layout_keeps_neighboring_columns_separate(self):
        stories = [
            Story('title1', [('Campus opens a new studio', 'Headline')], Box(1, 30, 60, 240, 80)),
            Story('title2', [('Local team opens its season', 'Headline')], Box(1, 260, 60, 470, 80)),
            Story('byline', [('By Mora Sampaio and Cynthia Maloney', 'Body')], Box(1, 30, 85, 220, 100)),
            Story('body1', [('The new studio opens Monday. ' * 8, 'Body')], Box(1, 30, 110, 240, 290)),
            Story('body2', [('The season starts on Friday. ' * 8, 'Body')], Box(1, 260, 110, 470, 290)),
            Story('caption', [('This is the caption. ' * 10, 'Photo Caption')], Box(1, 30, 300, 240, 350)),
        ]
        first, second = group_articles(stories, ElementTree.Element('Document'), {})
        self.assertEqual(first['authors'], ['Mora Sampaio', 'Cynthia Maloney'])
        self.assertIn('studio opens', first['body'])
        self.assertNotIn('caption', first['body'])
        self.assertIn('season starts', second['body'])
        self.assertEqual(second['authors'], [])
    def test_dotenv_credentials_are_used_only_on_server(self):
        path = app.DATA / '.env'
        path.write_text('# local settings\nWP_SITE=https://example.org/news/\n'
                        'WP_USERNAME=local-editor\nWP_APPLICATION_PASSWORD="abcd efgh"\n', encoding='utf-8-sig')
        self.a['reviewed'] = True
        self.a['authors'][0]['byline_only'] = True
        app.save(self.p)
        handler = object.__new__(app.Handler)
        handler.server = SimpleNamespace(server_port=8765)
        handler.headers = {'Host': '127.0.0.1:8765'}
        handler.send = Mock()
        with patch.object(app, 'ROOT', app.DATA):
            handler.path = '/api/wordpress'
            handler.do_GET()
            handler.send.assert_called_with(200, dict(site='https://example.org/news', configured=True))
            handler.path = '/.env'
            handler.do_GET()
            self.assertEqual(handler.send.call_args.args[0], 404)

            handler.headers['X-Workbench-Token'] = app.TOKEN
            with patch.object(app, 'wp_request', side_effect=[[], [], dict(id=44, status='draft')]) as request:
                handler.path = '/api/preflight'
                preview = json.dumps(dict(id=self.sid, article_ids=[self.a['id']])).encode()
                handler.headers['Content-Length'] = str(len(preview))
                handler.rfile = io.BytesIO(preview)
                handler.do_POST()
                status, result = handler.send.call_args.args
                self.assertEqual(status, 200)
                self.assertEqual(result['checks'][0]['errors'], [])
                signature = result['checks'][0]['signature']
                data = json.dumps(dict(id=self.sid, article_id=self.a['id'], site='https://example.org/news',
                                       signature=signature, connection=self.c)).encode()
                handler.headers['Content-Length'] = str(len(data))
                handler.path = '/api/draft'
                handler.rfile = io.BytesIO(data)
                handler.do_POST()
                self.assertEqual(handler.send.call_args.args[0], 200)
                self.assertEqual(request.call_count, 3)
                self.assertEqual(request.call_args.args[:4], ('https://example.org/news', 'posts', 'local-editor', 'abcd efgh'))
                self.assertEqual(request.call_args.args[4]['status'], 'draft')

            # Changing the configured site invalidates an already-open confirmation.
            path.write_text('WP_USERNAME=local-editor\nWP_APPLICATION_PASSWORD=abcd efgh\n', encoding='utf-8')
            with patch.object(app, 'wp_request') as request:
                handler.rfile = io.BytesIO(data)
                handler.do_POST()
                self.assertIn('site changed', handler.send.call_args.args[1]['error'])
                request.assert_not_called()

            path.write_text('', encoding='utf-8')
            handler.path = '/api/wordpress'
            handler.do_GET()
            handler.send.assert_called_with(200, dict(site=app.DEFAULT_SITE, configured=False))

    def test_prepare_issue_matches_unique_bylines_and_respects_category_removal(self):
        self.a.update(source_section='SPORTS', reviewed=True)
        other = app.article('Other headline', 'Ambiguous Name')
        other.update(source_section='SPORTS', categories_edited=True)
        self.p['articles'].append(other)
        allen = dict(name='Allen Worrell', handle='aw2362', wp_site=self.c['site'], wp_user_id=182)
        ambiguous = dict(name='Ambiguous Name', handle='amb1')

        def users(name, _connection):
            return [allen] if name == 'Allen Worrell' else [ambiguous, dict(ambiguous, handle='amb2')]

        with patch.object(app, 'search_wordpress_authors', side_effect=users), patch.object(
                app, 'wp_read', return_value=[dict(name='Sports', slug='sports')]):
            report = app.prepare_issue(self.p, self.c)
            self.assertEqual((report['linked'], report['suggested'], report['unresolved']), (1, 1, 1))
            self.assertEqual(self.a['categories'], ['Sports'])
            self.assertFalse(self.a['reviewed'])
            self.assertEqual(other['categories'], [])
            self.assertEqual(other['authors'][0]['handle'], '')
            self.a['categories'] = []
            app.prepare_issue(self.p, self.c)
        self.assertEqual(app.load(self.sid)['articles'][0]['categories'], [])

    def test_reviewed_batch_keeps_blocked_articles_and_only_posts_confirmed_drafts(self):
        self.a['authors'][0]['byline_only'] = True
        self.a['reviewed'] = True
        duplicate = app.article('Existing headline', 'Unresolved Name')
        duplicate.update(body='Another article body.', reviewed=True, tags=['missing-tag'])
        self.p['articles'].append(duplicate)
        app.save(self.p)
        app.set_active_issue(self.sid)
        handler = object.__new__(app.Handler)
        handler.server = SimpleNamespace(server_port=8765)
        handler.headers = {'Host': '127.0.0.1:8765', 'X-Workbench-Token': app.TOKEN}
        handler.send = Mock()

        def send(path, **payload):
            raw = json.dumps(dict(id=self.sid, **payload)).encode()
            handler.headers['Content-Length'] = str(len(raw))
            handler.rfile = io.BytesIO(raw)
            handler.path = path
            handler.do_POST()
            return handler.send.call_args.args[:2]

        def wordpress(_site, path, _username, _password, payload=None):
            if path == 'posts':
                self.assertEqual(payload['status'], 'draft')
                self.assertEqual(payload['title'], self.a['title'])
                return dict(id=90, status='draft')
            if path.startswith('posts?') and 'Existing+headline' in path:
                return [dict(id=21, title={'raw': 'Existing headline'}, status='draft')]
            return []

        with patch.object(app, 'wordpress_settings', return_value=self.c), patch.object(app, 'wp_request', side_effect=wordpress) as request:
            status, result = send('/api/preflight', article_ids=[self.a['id'], duplicate['id']], require_reviewed=True)
            self.assertEqual(status, 200)
            ready, blocked = result['checks']
            self.assertEqual(ready['errors'], [])
            self.assertIn('Link Unresolved Name', blocked['errors'][0])
            self.assertIn('missing-tag', blocked['errors'][1])
            self.assertEqual(blocked['duplicates'][0]['id'], 21)
            status, result = send('/api/draft', article_id=duplicate['id'], site=self.c['site'], signature=blocked['signature'])
            self.assertEqual(status, 400)
            self.assertIn('Unresolved Name', result['error'])
            status, result = send('/api/draft', article_id=self.a['id'], site=self.c['site'], signature=ready['signature'])
            self.assertEqual(status, 200)
            self.assertEqual(result['id'], 90)
        self.assertEqual(sum(call.args[1] == 'posts' for call in request.call_args_list), 1)
        pending = [a['id'] for a in app.load(self.sid)['articles'] if not a.get('wordpress_draft')]
        self.assertEqual(pending, [duplicate['id']])
    def test_local_font_route_serves_only_bundled_fonts(self):
        handler=object.__new__(app.Handler)
        handler.server=SimpleNamespace(server_port=8765)
        handler.headers={'Host':'127.0.0.1:8765'}
        handler.send=Mock()
        font=next((ROOT/'fonts').glob('*.ttf'))
        handler.path='/fonts/'+font.name
        handler.do_GET()
        handler.send.assert_called_with(200,font.read_bytes(),'font/ttf')
        for route in ('/fonts/../.env','/fonts/missing.ttf','/fonts/Inter-OFL.txt'):
            handler.path=route
            handler.do_GET()
            self.assertEqual(handler.send.call_args.args[0],404)

    def test_removed_export_and_copy_routes_return_not_found(self):
        handler=object.__new__(app.Handler)
        handler.server=SimpleNamespace(server_port=8765)
        handler.headers={'Host':'127.0.0.1:8765'}
        handler.send=Mock()
        handler.path='/export/'+self.sid
        handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],404)
        data=b'{}'
        handler.headers.update({'X-Workbench-Token':app.TOKEN,'Content-Length':str(len(data))})
        handler.rfile=io.BytesIO(data);handler.path='/api/text'
        handler.do_POST()
        self.assertEqual(handler.send.call_args.args[0],404)
    def test_non_article_pages_are_retained_off_queue(self):
        extra=app.article('Events calendar');extra['kind']='calendar';extra['body']='Saved calendar text'
        self.p['articles'].append(extra);app.save(self.p);stale=copy.deepcopy(self.p)
        loaded=app.load(self.sid)
        self.assertEqual(len(loaded['articles']),1)
        self.assertEqual(loaded['excluded_items'][0]['body'],'Saved calendar text')
        app.save_edits(stale)
        self.assertEqual(len(app.load(self.sid)['articles']),1)
    def test_non_article_cannot_be_sent_to_wordpress(self):
        self.a.update(kind='reference',reviewed=True)
        with patch.object(app,'wp_request') as request:
            with self.assertRaisesRegex(ValueError,'Only articles'):app.create_draft(self.p,self.a['id'],self.c)
            request.assert_not_called()
    def test_upgrade_resumes_saved_issue_with_articles(self):
        empty_id='b'*32;(app.DATA/empty_id).mkdir()
        app.save(dict(id=empty_id,name='Empty issue',articles=[]))
        self.assertEqual(app.active_issue_id(), self.sid)

    def test_json_project_is_migrated_to_sqlite(self):
        json_project=copy.deepcopy(self.p)
        json_project['name']='Migrated issue'
        app.save(json_project)
        app._REPOSITORY=None
        app._REPOSITORY_ROOT=None
        migrated=app.repository().load_project(self.sid)
        self.assertEqual(migrated['name'],'Migrated issue')

    def test_single_indd_close_and_reopen(self):
        raw = b'known INDD bytes'
        self.p['source_hash'] = hashlib.sha256(raw).hexdigest()
        self.a['title'] = 'Saved headline'
        app.save(self.p)
        handler = object.__new__(app.Handler)
        handler.server = SimpleNamespace(server_port=8765)
        handler.headers = {'Host': '127.0.0.1:8765', 'X-Workbench-Token': app.TOKEN}
        handler.send = Mock()

        def get(path):
            handler.path = path
            handler.do_GET()
            return handler.send.call_args.args[:2]

        def post(path, data):
            handler.path = path
            handler.rfile = io.BytesIO(data)
            handler.headers['Content-Length'] = str(len(data))
            handler.do_POST()
            return handler.send.call_args.args[:2]

        with patch.object(app, 'ROOT', app.DATA):
            self.assertEqual(get('/api/issue')[1]['project']['id'], self.sid)
            self.assertEqual(get('/api/projects')[0], 404)
            self.assertEqual(get('/api/project/' + self.sid)[0], 404)
            status, result = post('/api/indd', raw)
            self.assertEqual(status, 400)
            self.assertIn('Close the open INDD', result['error'])
            payload = json.dumps(dict(id=self.sid, article_id=self.a['id'])).encode()
            self.assertEqual(post('/api/close', payload)[0], 200)
            self.assertEqual(get('/api/issue'), (200, dict(project=None)))
            for path in ('/api/save', '/api/draft'):
                status, result = post(path, payload)
                self.assertEqual(status, 400)
                self.assertIn('no longer open', result['error'])
            status, result = post('/api/indd', b'unsupported file')
            self.assertEqual(status,202)
            import time
            for _ in range(40):
                job=app.import_job_status(result['job_id'])
                if job['state']!='running':break
                time.sleep(.025)
            self.assertEqual(job['state'],'failed')
            self.assertEqual(get('/api/issue'), (200, dict(project=None)))
            status, result = post('/api/indd', raw)
            self.assertEqual(status,202)
            for _ in range(40):
                job=app.import_job_status(result['job_id'])
                if job['state']!='running':break
                time.sleep(.025)
            self.assertEqual(job['state'],'done')
            result=job['project']
            self.assertEqual(result['id'], self.sid)
            self.assertEqual(result['articles'][0]['title'], 'Saved headline')

class LocalServerPolicyTests(unittest.TestCase):
    def test_strict_csp_and_requests_stay_protected(self):
        import http.client
        import threading
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
        try:
            for hostname in ('localhost', '127.0.0.1'):
                connection.request('GET', '/', headers={'Host': f'{hostname}:{server.server_port}'})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                policy = response.getheader('Content-Security-Policy')
                response.read()
                directives = dict(part.strip().split(' ', 1) for part in policy.split(';'))
                self.assertEqual(directives['default-src'], "'self'")
                self.assertEqual(directives['script-src'], "'self'")
                self.assertEqual(directives['connect-src'], "'self'")
                self.assertEqual(directives['style-src'], "'self'")
                self.assertEqual(directives['img-src'], "'self'")
                self.assertEqual(directives['frame-ancestors'], "'none'")
                self.assertEqual(directives['base-uri'], "'none'")
                connection.request('GET', '/', headers={'Host': 'untrusted.example'})
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
                connection.request('POST', '/api/save', body='{}', headers={
                    'Host': f'localhost:{server.server_port}',
                    'Origin': 'http://untrusted.example',
                    'X-Workbench-Token': app.TOKEN,
                    'Content-Type': 'application/json'})
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            worker.join()

if __name__=='__main__':unittest.main()
