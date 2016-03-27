import os
import sys
from StringIO import StringIO
import argparse
import getpass

from jira import JIRA
import xmltodict

from . import bugzilla


def sync_bz_to_jira(bz_server, bz_id, jira_server, project_key):
    '''
    issues_in_proj = jira.search_issues('project = project_key AND "BugZilla ID" ~ "%s"' % jira_id)
    found jira_id
    create new issue if not found
    create attachment if not exists, (use <desc>-<attachid> as filename)
    create comment if not exists
    '''
    bug = bugzilla.issue(bz_server, bz_id)

    print 'Bugzilla id %s found: %s' % (bz_id, bug.short_desc)

    user = raw_input("Username:")
    passwd = getpass.getpass()
    jira = JIRA(jira_server, basic_auth=(user, passwd))

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
        ans = raw_input("Update this issue? ")
        if ans not in ['y', 'Y', 'yes']:
            return
    else:
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
        if find_attachement(filename):
            continue
        jira.add_attachment(issue, StringIO(a.content), filename)
        print 'File %s attached' % filename

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


def main():
    parser = argparse.ArgumentParser(description='Convert Bugzilla issue to JIRA issue')
    parser.add_argument('bz_id', help='Bugzilla ID')
    parser.add_argument('-b', metavar='', help='Bugzilla Server URL')
    parser.add_argument('-j', metavar='', help='JIRA Server URL')
    parser.add_argument('-k', metavar='', help='JIRA Project Key')
    args = parser.parse_args()
    print args
    sync_bz_to_jira(args.b, args.bz_id, args.j, args.k)

if __name__ == '__main__':
    main() 
