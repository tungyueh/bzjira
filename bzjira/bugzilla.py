import requests
import xmltodict
import base64


def issue(bz_server, bz_id):
    resp = requests.get('%s/show_bug.cgi?ctype=xml&id=%s' % (bz_server, bz_id))
    resp.raise_for_status()
    return BZIssue(xmltodict.parse(resp.content))


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
