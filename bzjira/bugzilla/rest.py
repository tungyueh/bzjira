from urllib.parse import parse_qs
import base64

import requests


class RESTBugzilla(object):
    def __init__(self, bz_server):
        self.bz_server = bz_server
        self.token = None
        self.session = requests.Session()

    def login(self, username, passwd):
        resp = self.session.get(
            '%s/rest/login' % self.bz_server,
            params={
                'login': username,
                'password': passwd,
            }
        )
        resp.raise_for_status()
        content = resp.json()
        self.token = content['token']

    def _get_bug(self, bz_id):
        '''
        {
            bugs: [
                {
                    ...
                }
            ]
        }
        '''
        resp = self.session.get(
            '%s/rest/bug/%s' % (self.bz_server, bz_id),
            params={
                'token': self.token,
            }
        )
        resp.raise_for_status()
        return resp.json()

    def _get_comments(self, bz_id):
        '''
        {
            bugs: {
                $bz_id: {
                    comment: [
                        ...
                    ]
                }
            }
        }
        '''
        resp = self.session.get(
            '%s/rest/bug/%s/comment' % (self.bz_server, bz_id),
            params={
                'token': self.token,
            }
        )
        resp.raise_for_status()
        return resp.json()

    def _get_attachments(self, bz_id):
        '''
        {
           attachments : {},
           bugs : {
              $bz_id : [
                 {
                    ...
                 }
              ]
           }
        }
        '''
        resp = self.session.get(
            '%s/rest/bug/%s/attachment' % (self.bz_server, bz_id),
            params={
                'token': self.token,
            }
        )
        resp.raise_for_status()
        return resp.json()

    def issue(self, bz_id):
        bz_id = str(bz_id)
        # get bug body
        try:
            raw = self._get_bug(bz_id)
            bug = raw['bugs'][0]
        except requests.exceptions.HTTPError as exp:
            if exp.response.status_code != 404:
                raise
            # NOTE: Due to we have two bugzilla and for compatible reason they
            # the new bugzilla's start from 200000. so id not found may happen.
            # just ignore them until we have a better solution
            return None

        # and merge comments
        raw = self._get_comments(bz_id)
        bug['comments'] = raw['bugs'][bz_id]['comments']

        # and merge attachments
        raw = self._get_attachments(bz_id)
        bug['attachments'] = raw['bugs'][bz_id]
        return DQVBZIssue(bug)

    def buglist(self, query_string):
        params = parse_qs(query_string)
        params['token'] = self.token
        params['include_fields'] = 'id'
        resp = self.session.get(
            '%s/rest/bug' % (self.bz_server),
            params=params
        )
        resp.raise_for_status()
        for bug in resp.json()['bugs']:
            yield bug['id']


class BZIssue(object):
    def __init__(self, raw):
        self._raw = raw

    @property
    def bug_id(self):
        return self._raw['id']

    @property
    def priority(self):
        return self._raw['priority']

    @property
    def short_desc(self):
        return self._raw['summary']

    @property
    def status(self):
        return self._raw['status']

    @property
    def resolution(self):
        return self._raw['resolution']

    @property
    def long_desc(self):
        d = list()
        for comment in self._raw['comments']:
            d.append(LongDesc(comment))
        return d

    @property
    def attachment(self):
        a = list()
        for attachment in self._raw['attachments']:
            a.append(Attachment(attachment))
        return a


class DQVBZIssue(BZIssue):
    @property
    def short_desc(self):
        return u"[DQV#%s] %s" % (self.bug_id, self._raw['summary'])


class LongDesc(object):
    def __init__(self, raw):
        self._raw = raw

    @property
    def who(self):
        return self._raw['creator']

    @property
    def bug_when(self):
        return self._raw['time']

    @property
    def thetext(self):
        return self._raw['text']


class Attachment(object):
    def __init__(self, raw):
        self._raw = raw

    @property
    def attachid(self):
        return self._raw['id']

    @property
    def filename(self):
        return self._raw['file_name']

    @property
    def content(self):
        return base64.b64decode(self._raw['data'])
