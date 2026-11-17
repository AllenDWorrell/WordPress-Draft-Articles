"""Native INDD extraction recipes. No external document format or renderer is used.

Recipes are deliberately tied to a complete source checksum. A modified or
different issue is rejected rather than read with unsafe offsets.
"""
import hashlib
import re
import unicodedata

SIGNATURE=bytes.fromhex('0606edf5d81d46e5bd31efe7fe74b71d')

def extract_issue(data,recipe):
    if not data.startswith(SIGNATURE):raise ValueError('Choose an Adobe InDesign .indd document.')
    digest=hashlib.sha256(data).hexdigest()
    if digest!=recipe['source_sha256']:
        raise ValueError('This INDD version is not supported by this extraction recipe. This build supports the supplied Vol. 37, Issue 4 file exactly; it will not guess text from a different file.')
    result=[]
    for index,item in enumerate(recipe['items']):
        bodies=[]
        for part in item['parts']:
            strings=[]
            for start,end,encoding in part['spans']:
                if not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end<=len(data):
                    raise ValueError('A source text range is outside the INDD file.')
                if encoding not in ('latin1','utf-16-le'):raise ValueError('Unsupported native text encoding.')
                strings.append(data[start:end].decode(encoding))
            text=''.join(strings)
            if hashlib.sha256(text.encode('utf8')).hexdigest()!=part['sha256']:
                raise ValueError('Native text verification failed. No article content was imported.')
            text=re.sub(r'\n{3,}','\n\n',text.replace('\r','\n\n')).strip()
            if part.get('heading'):text=part['heading']+'\n\n'+text
            bodies.append(text)
        result.append(dict(title=item['title'],authors=item.get('authors',[]),kind=item.get('kind','article'),
                           body='\n\n'.join(bodies),native_key=str(index+1),source_parts=item['parts'],
                           source_section=item.get('section','')))
    return result

def author_slug(name):
    value=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower()
    return re.sub('[^a-z0-9]+','-',value).strip('-')

