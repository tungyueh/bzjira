import requests
import xmltodict
import base64


class Bugzilla(object):
    def __init__(self, bz_server):
        self.bz_server = bz_server
        self._cookie_jar = None
        self.session = requests.Session()
        a = requests.adapters.HTTPAdapter(max_retries=15)
        self.session.mount(bz_server, a)

    def login(self, username, passwd):
        resp = self.session.post('%s/index.cgi' % (self.bz_server), 
            data={
                'Bugzilla_login': username,
                'Bugzilla_password': passwd
            }
        )
        self._cookie_jar = resp.cookies 
        
    def issue(self, bz_id):
        resp = self.session.get('%s/show_bug.cgi?ctype=xml&id=%s' % (self.bz_server, bz_id),
                                cookies=self._cookie_jar)
        resp.raise_for_status()
        return DQVBZIssue(xmltodict.parse(resp.content))


    def buglist(self, query_string):
        resp = self.session.get('%s/buglist.cgi?ctype=rss&%s' % (self.bz_server, query_string),
                                cookies=self._cookie_jar)
        resp.raise_for_status()
        for entry in xmltodict.parse(resp.content)['feed']['entry']:
            yield entry['id'].split('=')[-1]


class BZIssue(object):
    def __init__(self, xmldict):
        self._raw = xmldict['bugzilla']['bug']

    @property
    def bug_id(self):
        return self._raw['bug_id']

    @property
    def priority(self):
        return self._raw['priority']

    @property
    def short_desc(self):
        return self._raw['short_desc']

    @property
    def status(self):
        return self._raw['bug_status']

    @property
    def long_desc(self):
        a = self._raw['long_desc']
        if isinstance(a, list):
            return [LongDesc(d) for d in a]
        else:
            return [LongDesc(a)]

    @property
    def attachment(self):
        a = self._raw.get('attachment')
        if not a:
            return []
        elif isinstance(a, list):
            return [Attachment(d) for d in a]
        else:
            return [Attachment(a)]


class DQVBZIssue(BZIssue):
    @property
    def short_desc(self):
        return u"[DQV#%s] %s" % (self.bug_id, self._raw['short_desc'])


class LongDesc(object):
    def __init__(self, raw):
        self._raw = raw

    @property
    def who(self):
        return self._raw['who']['@name']

    @property
    def bug_when(self):
        return self._raw['bug_when']

    @property
    def thetext(self):
        return self._raw['thetext']


class Attachment(object):
    def __init__(self, raw):
        self._raw = raw

    @property
    def attachid(self):
        return self._raw['attachid']

    @property
    def filename(self):
        return self._raw['filename']

    @property
    def content(self):
        return base64.b64decode(self._raw['data']['#text'])
