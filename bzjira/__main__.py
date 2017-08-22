import os
from StringIO import StringIO
import argparse
import getpass

from jira import JIRA
from requests.utils import get_netrc_auth
from . import bugzilla
from . import mantis


def sync_bz_to_jira(bz, bz_id, jira, project_key, yes_all):
    '''
    issues_in_proj = jira.search_issues('project = project_key AND "BugZilla ID" ~ "%s"' % jira_id)
    found jira_id
    create new issue if not found
    create attachment if not exists, (use <desc>-<attachid> as filename)
    create comment if not exists
    '''
    bug = bz.issue(bz_id)
    bz_server = bz.bz_server

    print 'Bugzilla id %s found: %s' % (bz_id, bug.short_desc)

    def create_issue(bug):
        issue = jira.create_issue(project=project_key,
                                  summary=bug.short_desc,
                                  description=bug.long_desc[0].thetext,
                                  issuetype={'name': 'Bug'},
                                  priority={'name': 'Critical' if bug.priority == 'P1' else 'Major'},
                                  customfield_10216=str(bug.bug_id))
        return issue

    issues = jira.search_issues('project = %s AND "BugZilla ID" ~ "%s"' % (project_key, bz_id))
    if issues:
        issue = issues[0]
        issue = jira.issue(issue.key)
        print 'Corresponding Jira issue found: %s' % issues[0]
        if str(issue.fields.status) == 'Closed':
           print 'Skip due to issue closed.'
           return
        if not yes_all:
            ans = raw_input("Update this issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
    else:
        if not yes_all:
            ans = raw_input("Create a new issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
        # create
        issue = create_issue(bug)
        print 'New Jira issue created: %s' % issue

    def find_attachement(filename):
        for a in issue.fields.attachment:
            if a.filename == filename:
                return a

    def find_comment(index):
        for c in issue.fields.comment.comments:
            first_line = c.body.split('\n', 1)[0]
            if first_line.endswith('c%d' % index):
                return c

    for a in bug.attachment:
        root, ext = os.path.splitext(a.filename)
        filename = '%s-%s%s' % (root, a.attachid, ext)
        if filename.encode('utf-8') != filename:
            import urllib2
            filename = urllib2.quote(filename.encode('utf-8'))
        if find_attachement(filename):
            continue
        jira.add_attachment(issue, StringIO(a.content), filename)
        print 'File %s (%d bytes)attached' % (filename, len(a.content))

    for i, c in enumerate(bug.long_desc):
        if i == 0:
            continue
        if find_comment(i):
            continue
        body = '''%s/show_bug.cgi?id=%s#c%d

{quote}
*%s %s*

%s
{quote}
        ''' % (bz_server, bz_id, i, c.who, c.bug_when, c.thetext)
        jira.add_comment(issue, body)
        print 'Comment %s created' % i

    if (bug.status in ['RESOLVED', 'VERIFIED'] and 
        str(issue.fields.status) not in ['Resolved', 'Verified', 'Closed']):
        resolution_map = {
            'FIXED': 'Fixed',
            'INVALID': 'Invalid',
            'WONTFIX': "Won't Fix",
            'LATER': 'Remind',
            'DUPLICATE': 'Duplicate',
            'WORKSFORME': 'Cannot Reproduce',
            'SpecChanged’: ‘Spec Changed’
        }
        jira.transition_issue(issue, 'Resolve Issue', 
        resolution={'name': resolution_map[bug.resolution]},
        comment='Change to Resolved due to Bugzilla #%s is %s' % (bz_id, bug.status))


def sync_mantis_to_jira(mantis_server, username, passwd, mantis_id, jira, project_key, yes_all):

    bug = mantis.issue(mantis_server, username, passwd, mantis_id)

    print 'Mantis id %s found: %s' % (mantis_id, bug.summary)

    def create_issue(bug):
        issue = jira.create_issue(project=project_key,
                                  summary='[Mantis#%s] ' % bug.id + bug.summary,
                                  description=bug.description,
                                  issuetype={'name': 'Bug'},
                                  priority={'name': 'Critical' if bug.priority == 'P1' else 'Major'},
                                  customfield_10216='Mantis-' + str(bug.id))
        return issue

    issues = jira.search_issues('project = %s AND "BugZilla ID" ~ "Mantis-%s"' % (project_key, mantis_id))
    if issues:
        issue = issues[0]
        issue = jira.issue(issue.key)
        print 'Corresponding Jira issue found: %s' % issues[0]
        if str(issue.fields.status) == 'Closed':
           print 'Skip due to issue closed.'
           return
        if not yes_all:
            ans = raw_input("Update this issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
    else:
        if not yes_all:
            ans = raw_input("Create a new issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
        # create
        issue = create_issue(bug)
        print 'New Jira issue created: %s' % issue

    def find_attachement(filename):
        # TODO: use filename as key?
        for a in issue.fields.attachment:
            if a.filename == filename:
                return a

    def find_comment(index):
        for c in issue.fields.comment.comments:
            first_line = c.body.split('\n', 1)[0]
            if first_line.endswith('c%d' % index):
                return c

    for a in bug.attachments:
        root, ext = os.path.splitext(a.filename)
        filename = '%s-%s%s' % (root, a.id, ext)
        if filename.encode('utf-8') != filename:
            import urllib2
            filename = urllib2.quote(filename.encode('utf-8'))
        if find_attachement(filename):
            continue
        try:
            content = StringIO(a.content)
        except:
            print '[ERROR] get attachment %s failed' % a
            continue
        aa = jira.add_attachment(issue, content, filename)
        print 'File %s (%d bytes)attached' % (filename, content.len)

    for i, c in enumerate(bug.notes):
        if find_comment(c.id):
            continue
        body = '''%s/view.php?id=%s#c%s

{quote}
*%s %s*

%s
{quote}
        ''' % (mantis_server, mantis_id, c.id, c.who, c.when, c.text)
        jira.add_comment(issue, body)
        print 'Comment %s created' % i

    if (bug.status in ['resolved', 'closed'] and
        str(issue.fields.status) not in ['Resolved', 'Verified', 'Closed']):
        jira.transition_issue(issue, 'Resolve Issue', 
        comment='Change to Resolved due to Mantis #%s is %s' % (mantis_id, bug.status))

def monkey_patch():
    import suds
    class MyXDateTime(suds.xsd.sxbuiltin.XDateTime):
        def translate(self, value, topython=True):
            value = value[:-2] + ':' + value[-2:]
            return super(MyXDateTime, self).translate(value, topython)
    suds.xsd.sxbuiltin.Factory.tags['dateTime'] = MyXDateTime


def main():
    parser = argparse.ArgumentParser(description='Convert Bugzilla/Mantis issue to JIRA issue')
    parser.add_argument('bz_id', help='Bugzilla ID')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-b', metavar='', help='Bugzilla Server URL')
    group.add_argument('-m', metavar='', help='Mantis Server URL')
    parser.add_argument('-j', metavar='', help='JIRA Server URL')
    parser.add_argument('-k', metavar='', help='JIRA Project Key')
    parser.add_argument('-y', action='store_true', default=False, help='Yes to all')
    parser.add_argument('-q', action='store_true', default=False, help='Query')
    parser.add_argument('-r', action='store_true', default=False, help='Revert')
    parser.add_argument('-p', metavar='', help='Mantis Project ID')
    parser.add_argument('-f', metavar='', help='Mantis Filter ID')
    args = parser.parse_args()


    jira_server = args.j
    if not get_netrc_auth(jira_server):
        user = raw_input("Jira Username:")
        passwd = getpass.getpass()
        jira = JIRA(jira_server, basic_auth=(user, passwd))
    else:
        jira = JIRA(jira_server)

    bz_server = args.b

    if args.b:  # bugzilla
        bz_server = args.b
        bz = bugzilla.Bugzilla(bz_server)
        auth = get_netrc_auth(bz_server)
        if not auth:
            bz_username = raw_input("Bugzilla Username:")
            bz_passwd = getpass.getpass()
        else:
            bz_username, bz_passwd = auth
        bz.login(bz_username, bz_passwd)
        if args.q:  # query
            bz_id_list = bz.buglist(args.bz_id)
            for bz_id in bz_id_list:
                sync_bz_to_jira(bz, bz_id, jira, args.k, args.y)
        elif args.r:  # find jira 
            issues = jira.search_issues('project = %s AND "BugZilla ID" is not empty '
            'AND status not in ("Resolved", "Closed", "Remind")' % (args.k))
            for issue in issues:
                bz_id = issue.fields.customfield_10216
                if bz_id.startswith('Mantis-'):
                    continue
                sync_bz_to_jira(bz, bz_id, jira, args.k, args.y)
        else:  # single bz id
            sync_bz_to_jira(bz, args.bz_id, jira, args.k, args.y)
    elif args.m:
        auth = get_netrc_auth(args.m)
        if not auth:
            username = raw_input("Username:")
            passwd = getpass.getpass()
        else:
            username, passwd = auth
        if args.p and args.f:
            for bz_id in mantis.filter_get_issues(args.m, username, passwd, args.p, args.f):
                sync_mantis_to_jira(args.m, username, passwd, bz_id, jira, args.k, args.y)
        elif args.r:  # find jira 
            issues = jira.search_issues('project = %s AND "BugZilla ID" is not empty '
            'AND status not in ("Resolved", "Closed", "Remind")' % (args.k))
            for issue in issues:
                bz_id = issue.fields.customfield_10216
                print bz_id
                if not bz_id.startswith('Mantis-'):
                    continue
                bz_id = bz_id.lstrip('Mantis-')
                print bz_id
                sync_mantis_to_jira(args.m, username, passwd, bz_id, jira, args.k, args.y)
        else:
            sync_mantis_to_jira(args.m, username, passwd, args.bz_id, jira, args.k, args.y)


if __name__ == '__main__':
    monkey_patch()
    main() 
