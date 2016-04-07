## Bugzilla to JIRA

Convert Bugzilla issue to JIRA issue using JIRA RESTful API.

## Usage

python -m bzjira -b \<Bugzilla URL\> -j \<JIRA URL\> -k \<PorjectKey\> \<Bugzilla ID\>

This tool is able to load the credentials from inside the ~/.netrc file, so put them there instead of input on console.

## netrc file format
machine <hostname> login <username> password <password>

e.g.
machine jira.myqnapcloud.com login harrychen password fakepassword
