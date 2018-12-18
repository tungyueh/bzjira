import requests

from .cgi import CGIBugzilla
from .rest import RESTBugzilla


class Bugzilla(object):
    def __init__(self, bz_server):
        self.bz_server = bz_server
        self._handler = None

    def __getattr__(self, key):
        return getattr(self._handler, key)

    def _is_support_rest(self):
        try:
            resp = requests.get('%s/rest/version' % self.bz_server)
            resp.raise_for_status()
            print('Bugzilla %s' % resp.json())
            return True
        except:
            print('Legacy bugzilla')
            return False

    def _get_handler(self):
        if self._is_support_rest():
            return RESTBugzilla(self.bz_server)
        else:
            return CGIBugzilla(self.bz_server)

    def login(self, username, passwd):
        if not self._handler:
            self._handler = self._get_handler()

        self._handler.login(username, passwd)
