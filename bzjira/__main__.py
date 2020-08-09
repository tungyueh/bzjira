import os
from io import BytesIO
import argparse
import getpass
from functools import partial

from jira import JIRA
from requests.utils import get_netrc_auth
from . import bugzilla
from . import mantis

MAX_OLD_JIRA_ATTACHMENT_BYTES = 10 * 1024 * 1024


def sync_new_jira_to_jira(new_jira_server, new_jira, bug, jira, project_key, yes_all):
    bz_id = bug.key
    if bug.fields.issuetype.name != 'Bug':
        print(f'New JIRA key {bz_id} skipped since type is not bug')
        return
    print('New JIRA key %s found: %s' % (bz_id, bug.fields.summary))
    comments = new_jira.comments(bug)
    attachments = bug.fields.attachment

    def create_issue(bug):
        issue = jira.create_issue(
            project=project_key,
            summary='[{}]{}'.format(bz_id.replace('-','#'), bug.fields.summary),
            description=bug.fields.description,
            issuetype={'name': 'Bug'},
            priority={'name': bug.fields.priority.name},
            customfield_14100=bz_id
        )
        return issue

    issues = jira.search_issues('project = %s AND "Mantis ID" ~ "%s"' % (project_key, bz_id))
    if issues:
        issue = issues[0]
        issue = jira.issue(issue.key)
        print('Corresponding Jira issue found: %s' % issues[0])
        if str(issue.fields.status) == 'Closed':
           print('Skip due to issue closed.')
           return
        if not yes_all:
            ans = input("Update this issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
    else:
        if not yes_all:
            ans = input("Create a new issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
        issue = create_issue(bug)
        print('New Jira issue created: %s' % issue)

    def find_attachment(filename):
        for a in issue.fields.attachment:
            if a.filename == filename:
                return a

    def find_attachment_comment(attach_id):
        for c in issue.fields.comment.comments:
            first_line = c.body.split('\n', 1)[0]
            if attach_id in first_line:
                return c

    for a in attachments:
        root, ext = os.path.splitext(a.filename)
        filename = '{}-{}{}'.format(root, a.id, ext)
        import urllib.request, urllib.error, urllib.parse
        filename = urllib.parse.quote(filename.encode('utf-8'))
        if len(filename) >= 255:
            ext_len = len(ext)
            filename = filename[:255-ext_len] + ext
            print('Filename too long, truncate to 255')
        if find_attachment(filename):
            continue

        if a.size > MAX_OLD_JIRA_ATTACHMENT_BYTES:
            if find_attachment_comment(a.id):
                continue
            downlaod_url = '%s/secure/attachment/%s/%s' % (new_jira_server, a.id, filename)
            comment = '{}\nbig attachment {}'.format(downlaod_url,
                                                     a.filename)
            jira.add_comment(issue, comment)
            print('Comment for file over 10MB:' + comment)
        else:
            jira.add_attachment(issue, BytesIO(a.get()), filename)
            print('File %s (%d bytes)attached' % (filename, a.size))

    def find_comment(comment_id):
        for c in issue.fields.comment.comments:
            first_line = c.body.split('\n', 1)[0]
            if first_line.endswith('#comment-%s' % comment_id):
                return c

    for c in comments:
        comment_id = c.id
        if find_comment(comment_id):
            continue
        body = '''%s/browse/%s?focusedCommentId=%s#comment-%s

{quote}
*%s %s*

%s
{quote}
        ''' % (new_jira_server, bz_id, comment_id, comment_id, c.author.displayName, c.created, c.body)
        jira.add_comment(issue, body)
        print('Comment %s created' % comment_id)

    bug_status = bug.fields.status.name.upper()
    if bug_status in ['VERIFIED', 'CLOSE', 'DONE', 'CLOSED']:
        if issue.fields.status.name == 'Open':
            jira.transition_issue(issue, 'Assign to')
        elif issue.fields.status.name == 'Assigned':
            jira.transition_issue(issue, 'Resolved',
                customfield_12044='NA', # build path
                fixVersions=[{'name':'NA'}],
                customfield_13443={'value':'---'}, # resolved reason
                customfield_12014='NA', # root cause
                customfield_11707='NA', # solution 
                comment='Change to Resolved due to JIRA #%s is %s' % (bz_id, bug.status))


def sync_bz_to_jira(bz, bz_id, jira, project_key, yes_all):
    '''
    issues_in_proj = jira.search_issues('project = project_key AND "BugZilla ID" ~ "%s"' % jira_id)
    found jira_id
    create new issue if not found
    create attachment if not exists, (use <desc>-<attachid> as filename)
    create comment if not exists
    '''
    bug = bz.issue(bz_id)
    if not bug:
        return
    bz_server = bz.bz_server

    print('Bugzilla id %s found: %s' % (bz_id, bug.short_desc))

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
        print('Corresponding Jira issue found: %s' % issues[0])
        if str(issue.fields.status) == 'Closed':
           print('Skip due to issue closed.')
           return
        if not yes_all:
            ans = input("Update this issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
    else:
        if not yes_all:
            ans = input("Create a new issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
        # create
        issue = create_issue(bug)
        print('New Jira issue created: %s' % issue)

    def find_attachment(filename):
        for a in issue.fields.attachment:
            if a.filename == filename:
                return a

    def find_comment(index):
        for c in issue.fields.comment.comments:
            first_line = c.body.split('\n', 1)[0]
            if first_line.endswith('c%d' % index):
                return c

    for a in bug.attachment:
        if not a.filename:
            print('skip attachment %s due to its name %s' % (a.attachid,
                                                             a.filename))
            continue

        root, ext = os.path.splitext(a.filename)
        filename = '%s-%s%s' % (root, a.attachid, ext)
        if filename.encode('utf-8') != filename:
            import urllib.request, urllib.error, urllib.parse
            filename = urllib.parse.quote(filename.encode('utf-8'))

        if len(filename) >= 255:
            ext_len = len(ext)
            filename = filename[:255-ext_len] + ext
            print('Filename too long, truncate to 255')

        if find_attachment(filename):
            continue
        if len(a.content) < MAX_OLD_JIRA_ATTACHMENT_BYTES:
            jira.add_attachment(issue, BytesIO(a.content), filename)
            print('File %s (%d bytes)attached' % (filename, len(a.content)))
        else:
            if find_attachment_comment(a.attachid):
                continue
            downlaod_url = bz.url + 'attachment.cgi?id=' + str(a.attachid)
            comment = '{}\nbig attachment {}'.format(downlaod_url,
                                                     a.attachid)
            jira.add_comment(issue, comment)
            print('Comment for file over 10MB:' + comment)

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
        print('Comment %s created' % i)

    if (bug.status in ['RESOLVED', 'VERIFIED'] and
        str(issue.fields.status) not in ['Resolved', 'Verified', 'Closed']):
        resolution_map = {
            'FIXED': 'Fixed',
            'INVALID': 'Invalid',
            'WONTFIX': "Won't Fix",
            'LATER': 'Remind',
            'DUPLICATE': 'Duplicate',
            'WORKSFORME': 'Cannot Reproduce',
            'SpecChanged': 'Spec Changed'
        }
        jira.transition_issue(issue, 'Resolve Issue',
        resolution={'name': resolution_map[bug.resolution]},
        comment='Change to Resolved due to Bugzilla #%s is %s' % (bz_id, bug.status))


def sync_mantis_to_jira(mantis_server, username, passwd, mantis_id, jira, project_key, board_id, yes_all):

    bug = mantis.issue(mantis_server, username, passwd, mantis_id)

    print('Mantis id %s found: %s' % (mantis_id, bug.summary))

    def create_issue(bug):
        issue = jira.create_issue(project=project_key,
                                  summary='[Mantis#%s] ' % bug.id + bug.summary,
                                  description=bug.description,
                                  issuetype={'name': 'Bug'},
                                  priority={'name': 'P3'},
                                  customfield_14100='Mantis-' + str(bug.id))
        return issue

    issues = jira.search_issues('project = %s AND "Mantis ID" ~ "Mantis-%s"' % (project_key, mantis_id))
    if issues:
        issue = issues[0]
        issue = jira.issue(issue.key)
        print('Corresponding Jira issue found: %s' % issues[0])
        if str(issue.fields.status) == 'Closed':
           print('Skip due to issue closed.')
           return
        if not yes_all:
            ans = input("Update this issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
    else:
        if not yes_all:
            ans = input("Create a new issue? ")
            if ans not in ['y', 'Y', 'yes']:
                return
        # create
        issue = create_issue(bug)
        print('New Jira issue created: %s' % issue)

    def find_attachment(filename):
        # TODO: use filename as key?
        for a in issue.fields.attachment:
            if a.filename == filename:
                return a

    def find_attachment_comment(attach_id):
        for c in issue.fields.comment.comments:
            first_line = c.body.split('\n', 1)[0]
            if first_line.endswith('=%s' % attach_id):
                return c

    def find_comment(index):
        for c in issue.fields.comment.comments:
            first_line = c.body.split('\n', 1)[0]
            if first_line.endswith('c%d' % index):
                return c

    def move_to_current_sprint(board_id, issue):
        for sprint in jira.sprints(board_id):
            if sprint.state == 'ACTIVE':
                cur_srpint = sprint
                break
        else:
            print('[WARN] cannot find active sprint on board %s for moving' % board_id)
            return
        jira.add_issues_to_sprint(sprint.id, [issue.key])
        print('Move issue %s to sprint %s' % (issue.key, sprint.name))

    for a in bug.attachments:
        root, ext = os.path.splitext(a.filename)
        if root.encode('utf-8') != root:
            import urllib.request, urllib.error, urllib.parse
            root = urllib.parse.quote(root.encode('utf-8'))
        if len(root) + len(str(a.id)) + len(ext) > 255:
            root = root[:255-len(str(a.id))-len(ext)-1]
        filename = '%s-%s%s' % (root, a.id, ext)
        if find_attachment(filename):
            continue
        try:
            content = BytesIO(a.content)
        except:
            print('[ERROR] get attachment %s failed' % a)
            continue
        content_len = content.getbuffer().nbytes
        if content_len < MAX_OLD_JIRA_ATTACHMENT_BYTES:
            aa = jira.add_attachment(issue, content, filename)
            print('File %s (%d bytes)attached' % (filename, content_len))
        else:
            if find_attachment_comment(a.id):
                continue
            downlaod_url = (mantis_server +
                            '/file_download.php?&type=bug&file_id=' +
                            str(a.id))
            comment = '{}\nbig attachment {}'.format(downlaod_url,
                                                     a.filename)
            jira.add_comment(issue, comment)
            print('Comment for file over 10MB:' + comment)

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
        print('Comment %s created' % i)
        if board_id:
            move_to_current_sprint(board_id, issue)

    if bug.status in ['resolved', 'closed']:
        if issue.fields.status.name == 'Open':
            jira.transition_issue(issue, 'Assign to')
        elif issue.fields.status.name == 'Assigned':
            jira.transition_issue(issue, 'Resolved',
                customfield_12044='NA', # build path
                fixVersions=[{'name':'NA'}],
                customfield_13443={'value':'---'}, # resolved reason
                customfield_12014='NA', # root cause
                customfield_11707='NA', # solution 
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
    group.add_argument('-nj', metavar='', help='New Jira Server URL')
    parser.add_argument('-j', metavar='', help='JIRA Server URL')
    parser.add_argument('-k', metavar='', help='JIRA Project Key')
    parser.add_argument('-o', metavar='', help='JIRA Board ID for moving commented issue to current sprint')
    parser.add_argument('-y', action='store_true', default=False, help='Yes to all')
    parser.add_argument('-q', action='store_true', default=False, help='Query')
    parser.add_argument('-r', action='store_true', default=False, help='Revert')
    parser.add_argument('-p', metavar='', help='Mantis Project ID')
    parser.add_argument('-f', metavar='', help='Mantis Filter ID')
    args = parser.parse_args()


    jira_server = args.j
    if not get_netrc_auth(jira_server):
        user = input("Jira Username:")
        passwd = getpass.getpass()
        jira = JIRA(jira_server, basic_auth=(user, passwd))
    else:
        jira = JIRA(jira_server)
    jira.search_issues = partial(jira.search_issues, maxResults=1000)

    bz_server = args.b

    if args.b:  # bugzilla
        bz_server = args.b
        bz = bugzilla.Bugzilla(bz_server)
        auth = get_netrc_auth(bz_server)
        if not auth:
            bz_username = input("Bugzilla Username:")
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
            'AND status not in ("Resolved", "Closed", "Remind", "Verified")' % (args.k))
            for issue in issues:
                bz_id = issue.fields.customfield_10216
                if bz_id.startswith('Mantis-'):
                    continue
                if bz_id.startswith('QTSHBS'):
                    continue
                try:
                    int(bz_id)
                except ValueError:
                    continue
                sync_bz_to_jira(bz, bz_id, jira, args.k, args.y)
        else:  # single bz id
            sync_bz_to_jira(bz, args.bz_id, jira, args.k, args.y)
    elif args.m:
        auth = get_netrc_auth(args.m)
        if not auth:
            username = input("Username:")
            passwd = getpass.getpass()
        else:
            username, passwd = auth
        if args.p and args.f:
            for bz_id in mantis.filter_get_issues(args.m, username, passwd, args.p, args.f):
                sync_mantis_to_jira(args.m, username, passwd, bz_id, jira, args.k, args.o, args.y)
        elif args.r:  # find jira
            issues = jira.search_issues('project = %s AND "BugZilla ID" is not empty '
            'AND status not in ("Resolved", "Closed", "Remind", "Verified")' % (args.k))
            for issue in issues:
                bz_id = issue.fields.customfield_10216
                if not bz_id.startswith('Mantis-'):
                    continue
                bz_id = bz_id.lstrip('Mantis-')
                sync_mantis_to_jira(args.m, username, passwd, bz_id, jira, args.k, args.o, args.y)
        else:
            sync_mantis_to_jira(args.m, username, passwd, args.bz_id, jira, args.k, args.o, args.y)
    elif args.nj:
        new_jira_server = args.nj
        if not get_netrc_auth(new_jira_server):
            user = input("New Jira Username:")
            passwd = getpass.getpass()
            new_jira = JIRA(new_jira_server, basic_auth=(user, passwd))
        else:
            new_jira = JIRA(new_jira_server)
        if args.q:  # query
            buglist = new_jira.search_issues(args.bz_id, startAt=0, maxResults=200)
            for bug_entry in buglist:
                bug = new_jira.issue(bug_entry.key)
                sync_new_jira_to_jira(new_jira_server, new_jira, bug, jira, args.k, args.y)
        elif args.r:  # find jira
            issues = jira.search_issues(
                'project = %s AND "Mantis ID" is not empty '
                'AND status not in ("Resolved", "Closed", "Remind", "Verified", "Abort")' % (
                    args.k))
            for issue in issues:
                bz_id = issue.fields.customfield_14100
                if not bz_id.startswith('QTSHBS00'):
                    continue
                bug = new_jira.issue(bz_id)
                sync_new_jira_to_jira(new_jira_server, new_jira, bug, jira, args.k, args.y)
        else:  # single jira id
            bug = new_jira.issue(args.bz_id)
            sync_new_jira_to_jira(new_jira_server, new_jira, bug, jira, args.k, args.y)

if __name__ == '__main__':
    monkey_patch()
    main()
