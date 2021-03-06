import sys, os, time
from cPickle import dump

from zope.interface import implements
from twisted.python import log
from twisted.web import html

from buildbot import interfaces, util
from buildbot.process.properties import Properties

class Change:
    """I represent a single change to the source tree. This may involve
    several files, but they are all changed by the same person, and there is
    a change comment for the group as a whole.

    If the version control system supports sequential repository- (or
    branch-) wide change numbers (like SVN, P4, and Arch), then revision=
    should be set to that number. The highest such number will be used at
    checkout time to get the correct set of files.

    If it does not (like CVS), when= should be set to the timestamp (seconds
    since epoch, as returned by time.time()) when the change was made. when=
    will be filled in for you (to the current time) if you omit it, which is
    suitable for ChangeSources which have no way of getting more accurate
    timestamps.

    The revision= and branch= values must be ASCII bytestrings, since they
    will eventually be used in a ShellCommand and passed to os.exec(), which
    requires bytestrings. These values will also be stored in a database,
    possibly as unicode, so they must be safely convertable back and forth.
    This restriction may be relaxed in the future.

    Changes should be submitted to ChangeMaster.addChange() in
    chronologically increasing order. Out-of-order changes will probably
    cause the web status displays to be corrupted."""

    implements(interfaces.IStatusEvent)

    number = None

    branch = None
    category = None
    revision = None # used to create a source-stamp

    def __init__(self, who, files, comments, isdir=0, links=None,
                 revision=None, when=None, branch=None, category=None,
                 revlink='', properties={}):
        self.who = who
        self.comments = comments
        self.isdir = isdir
        if links is None:
            links = []
        self.links = links

        self.revision = util.none_or_str(revision)
        if when is None:
            when = util.now()
        self.when = when
        self.branch = util.none_or_str(branch)
        self.category = util.none_or_str(category)
        self.revlink = revlink
        self.properties = Properties()
        self.properties.update(properties, "Change")

        # keep a sorted list of the files, for easier display
        self.files = files[:]
        self.files.sort()

    def __setstate__(self, dict):
        self.__dict__ = dict
        # Older Changes won't have a 'properties' attribute in them
        if not hasattr(self, 'properties'):
            self.properties = Properties()
        if not hasattr(self, 'revlink'):
            self.revlink = ""

    def asText(self):
        data = ""
        data += self.getFileContents()
        data += "At: %s\n" % self.getTime()
        data += "Changed By: %s\n" % self.who
        data += "Comments: %s" % self.comments
        data += "Properties: \n%s\n\n" % self.getProperties()
        return data

    def html_dict(self):
        '''returns a dictonary with suitable info for html/mail rendering'''
        files = []
        for file in self.files:
            link = filter(lambda s: s.find(file) != -1, self.links)
            if len(link) == 1:
                url = link[0]
            else:
                url = None
            files.append(dict(url=url, name=file))
        
        files = sorted(files, cmp=lambda a,b: a['name'] < b['name'])

        kwargs = { 'who'       : self.who,
                   'at'        : self.getTime(),
                   'files'     : files,
                   'rev'       : self.revision,
                   'revlink'   : getattr(self, 'revlink', None),
                   'branch'    : self.branch,
                   'comments'  : self.comments,
                   'properties': self.properties.asList(),
                   'number'    : self.number }

        return kwargs

    def asDict(self):
        result = {}
        # Constant
        result['number'] = self.number
        result['branch'] = self.branch
        result['category'] = self.category
        result['who'] = self.getShortAuthor()
        result['comments'] = self.comments
        result['revision'] = self.revision
        result['when'] = self.when
        result['files'] = self.files
        result['revlink'] = self.revlink
        result['properties'] = self.properties.asList()
        return result

    def getShortAuthor(self):
        return self.who

    def getTime(self):
        if not self.when:
            return "?"
        return time.strftime("%a %d %b %Y %H:%M:%S",
                             time.localtime(self.when))

    def getTimes(self):
        return (self.when, None)

    def getText(self):
        return [html.escape(self.who)]
    def getLogs(self):
        return {}

    def getFileContents(self):
        data = ""
        if len(self.files) == 1:
            if self.isdir:
                data += "Directory: %s\n" % self.files[0]
            else:
                data += "File: %s\n" % self.files[0]
        else:
            data += "Files:\n"
            for f in self.files:
                data += " %s\n" % f
        return data

    def getProperties(self):
        data = ""
        for prop in self.properties.asList():
            data += "  %s: %s" % (prop[0], prop[1])
        return data


class ChangeMaster:
    # this is a stub, retained to allow the "buildbot upgrade-master" tool to
    # read old changes.pck pickle files and convert their contents into the
    # new database format. This is only instantiated by that tool, or by
    # test_db.py which tests that tool. The functionality that previously
    # lived here has been moved into buildbot.changes.manager.ChangeManager

    def __init__(self):
        self.changes = []
        # self.basedir must be filled in by the parent
        self.nextNumber = 1

    def addChange(self, change):
        change.number = self.nextNumber
        self.nextNumber += 1
        self.changes.append(change)

    def saveYourself(self):
        filename = os.path.join(self.basedir, "changes.pck")
        tmpfilename = filename + ".tmp"
        try:
            dump(self, open(tmpfilename, "wb"))
            if sys.platform == 'win32':
                # windows cannot rename a file on top of an existing one
                if os.path.exists(filename):
                    os.unlink(filename)
            os.rename(tmpfilename, filename)
        except Exception:
            log.msg("unable to save changes")
            log.err()

class OldChangeMaster(ChangeMaster):
    # this is a reminder that the ChangeMaster class is old
    pass
# vim: set ts=4 sts=4 sw=4 et:
