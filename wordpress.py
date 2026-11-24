"""WordPress REST adapter and local credential loading."""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import ctypes
from ctypes import wintypes
from pathlib import Path

try:
    import keyring
except ImportError:
    keyring=None


KEYRING_SERVICE='The Current - WordPress'
USERNAME_KEY='username'
PASSWORD_KEY='application-password'
CRED_TYPE_GENERIC=1
CRED_PERSIST_LOCAL_MACHINE=2


class FILETIME(ctypes.Structure):
    _fields_=[('dwLowDateTime',wintypes.DWORD),
              ('dwHighDateTime',wintypes.DWORD)]


class CREDENTIAL(ctypes.Structure):
    _fields_=[('Flags',wintypes.DWORD),
              ('Type',wintypes.DWORD),
              ('TargetName',wintypes.LPWSTR),
              ('Comment',wintypes.LPWSTR),
              ('LastWritten',FILETIME),
              ('CredentialBlobSize',wintypes.DWORD),
              ('CredentialBlob',ctypes.POINTER(wintypes.BYTE)),
              ('Persist',wintypes.DWORD),
              ('AttributeCount',wintypes.DWORD),
              ('Attributes',ctypes.c_void_p),
              ('TargetAlias',wintypes.LPWSTR),
              ('UserName',wintypes.LPWSTR)]


def windows_supported():
    return os.name=='nt' and hasattr(ctypes,'windll')


def credential_target(key):
    return f'{KEYRING_SERVICE}/{key}'


def windows_credential_read(key):
    if not windows_supported():
        return ''
    advapi32=ctypes.windll.Advapi32
    advapi32.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
                                 ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    advapi32.CredReadW.restype=wintypes.BOOL
    advapi32.CredFree.argtypes=[ctypes.c_void_p]
    advapi32.CredFree.restype=None
    credential=ctypes.POINTER(CREDENTIAL)()
    if not advapi32.CredReadW(credential_target(key),CRED_TYPE_GENERIC,0,
                              ctypes.byref(credential)):
        return ''
    try:
        size=credential.contents.CredentialBlobSize
        blob=ctypes.string_at(credential.contents.CredentialBlob,size)
        return blob.decode('utf-16-le')
    finally:
        advapi32.CredFree(credential)


def windows_credential_write(key,value):
    if not windows_supported():
        raise ValueError('Windows Credential Manager is unavailable on this system.')
    blob=value.encode('utf-16-le')
    buffer=(wintypes.BYTE * len(blob)).from_buffer_copy(blob)
    credential=CREDENTIAL(
        0,CRED_TYPE_GENERIC,credential_target(key),None,FILETIME(),
        len(blob),ctypes.cast(buffer,ctypes.POINTER(wintypes.BYTE)),
        CRED_PERSIST_LOCAL_MACHINE,0,None,None,None,
    )
    advapi32=ctypes.windll.Advapi32
    advapi32.CredWriteW.argtypes=[ctypes.POINTER(CREDENTIAL),wintypes.DWORD]
    advapi32.CredWriteW.restype=wintypes.BOOL
    if not advapi32.CredWriteW(ctypes.byref(credential),0):
        raise ctypes.WinError()


def windows_credential_delete(key):
    if not windows_supported():
        return
    advapi32=ctypes.windll.Advapi32
    advapi32.CredDeleteW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD]
    advapi32.CredDeleteW.restype=wintypes.BOOL
    advapi32.CredDeleteW(credential_target(key),CRED_TYPE_GENERIC,0)


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
    if keyring is not None:
        try:
            username=keyring.get_password(KEYRING_SERVICE,USERNAME_KEY) or ''
            password=keyring.get_password(KEYRING_SERVICE,PASSWORD_KEY) or ''
            return dict(configured=bool(username and password.replace(' ','')),
                        backend_available=True)
        except Exception:
            pass
    try:
        username=windows_credential_read(USERNAME_KEY)
        password=windows_credential_read(PASSWORD_KEY)
        return dict(configured=bool(username and password.replace(' ','')),
                    backend_available=bool(windows_supported()))
    except Exception:
        return dict(configured=False,backend_available=False)


def get_credentials(default_site):
    status=credential_status()
    if not status['backend_available']:
        return dict(site=default_site,username='',password='')
    try:
        if keyring is not None:
            username=keyring.get_password(KEYRING_SERVICE,USERNAME_KEY) or ''
            password=keyring.get_password(KEYRING_SERVICE,PASSWORD_KEY) or ''
        else:
            username=windows_credential_read(USERNAME_KEY)
            password=windows_credential_read(PASSWORD_KEY)
    except Exception:
        username=windows_credential_read(USERNAME_KEY)
        password=windows_credential_read(PASSWORD_KEY)
    return dict(site=default_site,username=username,password=password)


def save_credentials(site,username,password):
    site=(site or '').strip().rstrip('/')
    validate_site(site)
    username=username.strip()
    password=password.strip()
    if not username or not password.replace(' ',''):
        raise ValueError('Enter both a WordPress username and application password.')
    if keyring is not None:
        try:
            keyring.set_password(KEYRING_SERVICE,USERNAME_KEY,username)
            keyring.set_password(KEYRING_SERVICE,PASSWORD_KEY,password)
            return
        except Exception:
            pass
    try:
        windows_credential_write(USERNAME_KEY,username)
        windows_credential_write(PASSWORD_KEY,password)
    except Exception as error:
        raise ValueError('Could not store credentials in Windows Credential Manager.') from error


def delete_credentials():
    if keyring is None:
        pass
    else:
        for key in (PASSWORD_KEY,USERNAME_KEY):
            try:
                keyring.delete_password(KEYRING_SERVICE,key)
            except Exception:
                pass
    windows_credential_delete(USERNAME_KEY)
    windows_credential_delete(PASSWORD_KEY)


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
