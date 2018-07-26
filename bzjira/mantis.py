import base64

from suds.client import Client
from suds.bindings.binding import Binding
Binding.replyfilter = (lambda s,r: r.replace('\x08', ''))

def issue(mantis_server, username, passwd, mantis_id):
    client = Client(mantis_server + '/api/soap/mantisconnect.php?wsdl')
    resp = client.service.mc_issue_get(username, passwd, mantis_id)
    i = MantisIssue(resp, mantis_server, username, passwd)
    return i


def filter_get_issues(mantis_server, username, passwd, project_id, filter_id,
                      page_num=1, per_page=10000):
    client = Client(mantis_server + '/api/soap/mantisconnect.php?wsdl')
    resp = client.service.mc_filter_get_issues(username, passwd, project_id,
                                               filter_id, page_num, per_page)
    for i in resp:
        yield i.id


class MantisIssue(object):
    def __init__(self, raw, mantis_server, username, passwd):
        self._raw = raw
        self.mantis_server = mantis_server
        self.username = username
        self.passwd = passwd

    @property
    def id(self):
        return self._raw.id

    @property
    def priority(self):
        # normal, TBD
        return self._raw.priority.name

    @property
    def summary(self):
        return self._raw.summary

    @property
    def description(self):
        return '\n'.join([self._raw.description,
                          self._raw.additional_information])


    @property
    def status(self):
        return self._raw.status.name

    @property
    def notes(self):
        # not every issue has comments(notes)
        if not hasattr(self._raw, 'notes'):
            return []
        a = self._raw.notes
        return [Note(d) for d in a]

    @property
    def attachments(self):
        a = self._raw.attachments
        return [Attachment(d, self) for d in a]


class Note(object):
    def __init__(self, raw):
        self._raw = raw

    @property
    def id(self):
        return self._raw.id

    @property
    def who(self):
        if hasattr(self._raw.reporter, 'name'):
            return self._raw.reporter.name
        else:
             return 'NoName(%s)' % self._raw.reporter.id

    @property
    def when(self):
        return self._raw.last_modified

    @property
    def text(self):
        return self._raw.text


class Attachment(object):
    def __init__(self, raw, issue):
        self._raw = raw
        self._issue = issue

    @property
    def id(self):
        return self._raw.id

    @property
    def filename(self):
        return self._raw.filename

    @property
    def content(self):
        client = Client(self._issue.mantis_server + '/api/soap/mantisconnect.php?wsdl')
        resp = client.service.mc_issue_attachment_get(self._issue.username,
                                                      self._issue.passwd,
                                                      self.id)
        return base64.b64decode(resp)
