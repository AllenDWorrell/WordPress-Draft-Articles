"""WordPress REST adapter and local credential loading."""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import keyring
except ImportError:
    keyring=None


KEYRING_SERVICE='The Current - WordPress'
USERNAME_KEY='username'
PASSWORD_KEY='application-password'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('WordPress redirected the request. Use the final HTTPS site address; credentials were not forwarded.')


class WordPressError(ValueError):
    def __init__(self,status,message):
        self.status=status
        super().__init__(f'WordPress returned {status}: {message}')


def load_settings(root,default_site):
    fields={'WP_SITE':'site','WP_USERNAME':'username','WP_APPLICATION_PASSWORD':'password'}
    settings=dict(site=default_site,username='',password='')
    try:
        lines=(Path(root)/'.env').read_text(encoding='utf-8-sig').splitlines()
    except FileNotFoundError:
        return settings
    except (OSError,UnicodeError):
        raise ValueError('Could not read .env. Save it as a UTF-8 text file beside app.py.') from None
    for line in lines:
        key,separator,value=line.partition('=')
        key=key.strip()
        if separator and key in fields:
            value=value.strip()
            if len(value)>=2 and value[0] in ('"',"'") and value[-1]==value[0]:
                value=value[1:-1].strip()
            settings[fields[key]]=value
    settings['site']=(settings['site'] or default_site).rstrip('/')
    return settings


def wordpress_ready(settings):
    return bool(settings['username'] and settings['password'].replace(' ',''))


def credential_status():
    if keyring is None:
        return dict(configured=False,backend_available=False)
    try:
        username=keyring.get_password(KEYRING_SERVICE,USERNAME_KEY) or ''
        password=keyring.get_password(KEYRING_SERVICE,PASSWORD_KEY) or ''
        return dict(configured=bool(username and password.replace(' ','')),
                    backend_available=True)
    except Exception:
        return dict(configured=False,backend_available=False)


def get_credentials(default_site):
    status=credential_status()
    if not status['backend_available']:
        return dict(site=default_site,username='',password='')
    try:
        username=keyring.get_password(KEYRING_SERVICE,USERNAME_KEY) or ''
        password=keyring.get_password(KEYRING_SERVICE,PASSWORD_KEY) or ''
    except Exception:
        return dict(site=default_site,username='',password='')
    return dict(site=default_site,username=username,password=password)


def save_credentials(site,username,password):
    if keyring is None:
        raise ValueError('Windows Credential Manager support is unavailable.')
    site=(site or '').strip().rstrip('/')
    validate_site(site)
    username=username.strip()
    password=password.strip()
    if not username or not password.replace(' ',''):
        raise ValueError('Enter both a WordPress username and application password.')
    try:
        keyring.set_password(KEYRING_SERVICE,USERNAME_KEY,username)
        keyring.set_password(KEYRING_SERVICE,PASSWORD_KEY,password)
    except Exception as error:
        raise ValueError('Could not store credentials in Windows Credential Manager.') from error


def delete_credentials():
    if keyring is None:
        return
    for key in (PASSWORD_KEY,USERNAME_KEY):
        try:
            keyring.delete_password(KEYRING_SERVICE,key)
        except Exception:
            pass


def validate_site(site):
    try:
        parsed=urllib.parse.urlsplit(site)
        valid=(parsed.scheme=='https' and parsed.hostname and parsed.username is None
               and parsed.password is None and not re.search(r'[\s\\?#]',site))
        parsed.port
    except ValueError:
        valid=False
    if not valid:
        raise ValueError('Set WP_SITE in .env to an HTTPS site URL without login details, a query, or a fragment.')


def request(base,path,username,password,payload=None,content_type='application/json',filename=None):
    validate_site(base)
    if not username or not password.replace(' ',''):
        raise ValueError('Fill in WP_USERNAME and WP_APPLICATION_PASSWORD in the .env file beside app.py.')
    url=base.rstrip('/')+'/wp-json/wp/v2/'+path
    auth=base64.b64encode((username+':'+password.replace(' ','')).encode()).decode()
    headers={'Authorization':'Basic '+auth,'Content-Type':content_type,
             'User-Agent':'CurrentDraftWorkbench/1.0'}
    if filename:
        headers['Content-Disposition']='attachment; filename="'+filename+'"'
    req=urllib.request.Request(
        url,
        data=payload if isinstance(payload,bytes) else json.dumps(payload).encode()
             if payload is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        try:
            message=json.load(err).get('message','Request rejected.')
        except Exception:
            message='Request rejected.'
        raise WordPressError(err.code,message) from None
