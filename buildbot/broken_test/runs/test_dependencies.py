# -*- test-case-name: buildbot.broken_test.test_dependencies -*-

from twisted.trial import unittest

from buildbot.broken_test.runutils import MasterMixin, StallMixin
from buildbot.status import base
from buildbot.changes.changes import Change

config_1 = """
from buildbot import scheduler
from buildbot.process import factory
from buildbot.steps import dummy
from buildbot.buildslave import BuildSlave
s = factory.s
from buildbot.config import BuilderConfig

BuildmasterConfig = c = {}
c['slaves'] = [BuildSlave('bot1', 'sekrit'), BuildSlave('bot2', 'sekrit')]
c['schedulers'] = []
c['slavePortnum'] = 0

# upstream1 (fastfail, slowpass)
#  -> downstream2 (b3, b4)
# upstream3 (slowfail, slowpass)
#  -> downstream4 (b3, b4)
#  -> downstream5 (b5)

def fimp1(c):
    return bool(c.files)
def fimp2(c):
    return not fimp1(c)

s1 = scheduler.Scheduler('upstream1', None, None, ['slowpass', 'fastfail'],
                         fileIsImportant=fimp1)
s2 = scheduler.Dependent('downstream2', s1, ['b3', 'b4'])
s3 = scheduler.Scheduler('upstream3', None, None, ['fastpass', 'slowpass'],
                         fileIsImportant=fimp2)
s4 = scheduler.Dependent('downstream4', s3, ['b3', 'b4'])
s5 = scheduler.Dependent('downstream5', s4, ['b5'])
c['schedulers'] = [s1, s2, s3, s4, s5]

f_fastpass = factory.BuildFactory([s(dummy.Dummy, timeout=1)])
f_slowpass = factory.BuildFactory([s(dummy.Dummy, timeout=2)])
f_fastfail = factory.BuildFactory([s(dummy.FailingDummy, timeout=1)])

def builder(name, f):
    return BuilderConfig(
        name=name,
        slavename='bot1',
        factory=f)

c['builders'] = [builder('slowpass', f_slowpass),
                 builder('fastfail', f_fastfail),
                 builder('fastpass', f_fastpass),
                 builder('b3', f_fastpass),
                 builder('b4', f_fastpass),
                 builder('b5', f_fastpass),
                 ]
"""

class Logger(base.StatusReceiverMultiService):
    def __init__(self, master):
        base.StatusReceiverMultiService.__init__(self)
        self.builds = []
        for bn in master.status.getBuilderNames():
            master.status.getBuilder(bn).subscribe(self)

    def buildStarted(self, builderName, build):
        self.builds.append(builderName)

class Dependencies(MasterMixin, StallMixin, unittest.TestCase):

    def testParse(self):
        self.basedir = "dependencies/Dependencies/parse"
        self.create_master()
        d = self.master.loadConfig(config_1)
        # that's it, just make sure this config file is loaded successfully
        return d

    def testRun_Fail(self):
        self.basedir = "dependencies/Dependencies/run_fail"
        self.create_master()
        d = self.master.loadConfig(config_1)
        d.addCallback(lambda ign:
                      self.connectSlave(["slowpass", "fastfail", "fastpass",
                                         "b3", "b4", "b5"]))
        def _then(ign):
            # add an extra status target to make pay attention to which builds
            # start and which don't.
            self.logger = Logger(self.master)

            # kick off upstream1, which has a failing Builder and thus will
            # not trigger downstream3. We hit upstream1 (and not upstream3)
            # by using a Change with some files.
            c = Change("warner", ["foo.py"], "comments")
            self.master.change_svc.addChange(c)
            # t=0: two builders start: 'slowpass' and 'fastfail'
            # t=1: builder 'fastfail' finishes
            # t=2: builder 'slowpass' finishes
        d.addCallback(_then)
        d.addCallback(self.stall, 5.0)
        d.addCallback(self._testRun_Fail_1)
        return d

    def _testRun_Fail_1(self, res):
        # 'slowpass' and 'fastfail' should have run one build each
        b = self.status.getBuilder('slowpass').getLastFinishedBuild()
        self.failUnless(b)
        self.failUnlessEqual(b.getNumber(), 0)
        b = self.status.getBuilder('fastfail').getLastFinishedBuild()
        self.failUnless(b)
        self.failUnlessEqual(b.getNumber(), 0)

        # none of the other builders should have run
        self.failIf(self.status.getBuilder('b3').getLastFinishedBuild())
        self.failIf(self.status.getBuilder('b4').getLastFinishedBuild())
        self.failIf(self.status.getBuilder('b5').getLastFinishedBuild())

        # in fact, none of them should have even started
        self.failUnlessEqual(len(self.logger.builds), 2)
        self.failUnless("slowpass" in self.logger.builds)
        self.failUnless("fastfail" in self.logger.builds)
        self.failIf("b3" in self.logger.builds)
        self.failIf("b4" in self.logger.builds)
        self.failIf("b5" in self.logger.builds)

    def testRun_Pass(self):
        self.basedir = "dependencies/Dependencies/run_pass"
        self.create_master()
        d = self.master.loadConfig(config_1)
        d.addCallback(lambda ign:
                      self.connectSlave(["slowpass", "fastfail", "fastpass",
                                         "b3", "b4", "b5"]))
        def _then(ign):
            # kick off upstream3, which will fire downstream4 and then
            # downstream5
            c = Change("warner", [], "comments")
            self.master.change_svc.addChange(c)
            # t=0: slowpass and fastpass start
            # t=1: builder 'fastpass' finishes
            # t=2: builder 'slowpass' finishes
            #      scheduler 'downstream4' fires
            #      builds b3 and b4 are started
            # t=3: builds b3 and b4 finish
            #      scheduler 'downstream5' fires
            #      build b5 is started
            # t=4: build b5 is finished
        d.addCallback(_then)
        d.addCallback(self.stall, 5.0)
        d.addCallback(self._testRun_Pass_1)
        return d

    def _testRun_Pass_1(self, res):
        # 'fastpass' and 'slowpass' should have run one build each
        b = self.status.getBuilder('fastpass').getLastFinishedBuild()
        self.failUnless(b)
        self.failUnlessEqual(b.getNumber(), 0)

        b = self.status.getBuilder('slowpass').getLastFinishedBuild()
        self.failUnless(b)
        self.failUnlessEqual(b.getNumber(), 0)

        self.failIf(self.status.getBuilder('fastfail').getLastFinishedBuild())

        b = self.status.getBuilder('b3').getLastFinishedBuild()
        self.failUnless(b)
        self.failUnlessEqual(b.getNumber(), 0)

        b = self.status.getBuilder('b4').getLastFinishedBuild()
        self.failUnless(b)
        self.failUnlessEqual(b.getNumber(), 0)

        b = self.status.getBuilder('b4').getLastFinishedBuild()
        self.failUnless(b)
        self.failUnlessEqual(b.getNumber(), 0)
