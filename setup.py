from setuptools import setup, find_packages

setup(
    name = "bzjira",
    version = "0.1.0",
    packages=find_packages(exclude=["test", "test.*"]),

    install_requires = [
        'jira', 'xmltodict'
    ],
    author = "Harry Chen",
    author_email = "cjhecm@gmail.com",
    description=('Convert Bugzilla issue to Jira issue')
)
