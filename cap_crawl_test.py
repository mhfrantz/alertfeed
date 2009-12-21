#!/usr/bin/python2.4
#
# Copyright 2009 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for cap_crawl."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import __builtin__
import datetime
import os
import time

import google3
import mox

from google3.apphosting.ext import db
from google3.apphosting.ext import webapp
from google3.apphosting.runtime.apiproxy_errors import DeadlineExceededError
from google3.pyglib import app
from google3.pyglib import resources
from google3.testing.pybase import googletest

from google3.dotorg.gongo.appengine_cap2kml import cap_crawl
from google3.dotorg.gongo.appengine_cap2kml import cap_index_parse
from google3.dotorg.gongo.appengine_cap2kml import cap_parse_mem
from google3.dotorg.gongo.appengine_cap2kml import cap_schema
from google3.dotorg.gongo.appengine_cap2kml import cap_test_util
from google3.dotorg.gongo.appengine_cap2kml import db_test_util
from google3.dotorg.gongo.appengine_cap2kml import fake_clock
from google3.dotorg.gongo.appengine_cap2kml import mox_util
from google3.dotorg.gongo.appengine_cap2kml import taskqueue_test_util


class CapCrawlTestBase(mox.MoxTestBase, db_test_util.DbTestBase):
  """Base class for all cap_crawl unit tests."""

  def setUp(self):
    super(CapCrawlTestBase, self).setUp()
    # Stub out anything that we never want to call for real.
    self.mox.StubOutWithMock(cap_crawl, 'urlfetch')
    self.mox.StubOutWithMock(cap_crawl, 'logging')
    self.mox.StubOutWithMock(cap_crawl, 'random')
    self.mox.StubOutWithMock(time, 'sleep')
    self.mox.StubOutWithMock(cap_crawl, '_EnqueuePush')
    self.mox.StubOutWithMock(cap_crawl, '_EnqueueShard')


class MakeAtomFeedTest(CapCrawlTestBase):
  """Tests for cap_crawl._MakeAtomFeed."""

  def testMakeAtomFeed_nominal(self):
    urls = ['url1', 'url2', 'url3', 'url4']
    entries = ('<atom:entry><atom:link href="url1" /></atom:entry>\n'
               '  <atom:entry><atom:link href="url2" /></atom:entry>\n'
               '  <atom:entry><atom:link href="url3" /></atom:entry>\n'
               '  <atom:entry><atom:link href="url4" /></atom:entry>')
    expected = cap_crawl._ATOM_INDEX % dict(entries=entries)
    actual = cap_crawl._MakeAtomFeed(urls)
    self.assertMultiLineEqual(actual, expected)

    # Make sure it is a valid CAP index.
    self.assertListEqual(cap_index_parse.ParseCapIndex(actual), urls)


class FetchUrlTest(CapCrawlTestBase):
  """Tests for cap_crawl.FetchUrl."""

  def testFetchUrl_testdata(self):
    self.assertEquals(
        cap_crawl.FetchUrl('testdata/rss_feed1.xml'),
        resources.GetResource(os.path.join('google3', 'dotorg', 'gongo',
                                           'appengine_cap2kml', 'testdata',
                                           'rss_feed1.xml')))

  def testFetchUrl_testdataMissingFile(self):
    cap_crawl.logging.error(mox.StrContains('Cannot read file'),
                             mox.StrContains('testdata/foo'))
    self.mox.ReplayAll()

    self.assertRaises(IOError, cap_crawl.FetchUrl, 'testdata/foo')

  def testFetchUrl_testdataDeadlineExceededBeforeOpen(self):
    self.mox.StubOutWithMock(__builtin__, 'open')
    open(mox.IgnoreArg(), mode='r').AndRaise(DeadlineExceededError)
    self.mox.ReplayAll()

    self.assertRaises(DeadlineExceededError,
                      cap_crawl.FetchUrl, 'testdata/foo')

  def testFetchUrl_testdataDeadlineExceededAfterOpen(self):
    self.mox.StubOutWithMock(__builtin__, 'open')
    fd = self.mox.CreateMockAnything()
    open(mox.IgnoreArg(), mode='r').AndReturn(fd)
    fd.read().AndRaise(DeadlineExceededError)
    fd.close()
    self.mox.ReplayAll()

    self.assertRaises(DeadlineExceededError,
                      cap_crawl.FetchUrl, 'testdata/foo')

  def testFetchUrl_testdataReadError(self):
    self.mox.StubOutWithMock(__builtin__, 'open')
    fd = self.mox.CreateMockAnything()
    open(mox.IgnoreArg(), mode='r').AndReturn(fd)
    fd.read().AndRaise(IOError)
    fd.close()
    cap_crawl.logging.error(mox.StrContains('Cannot read file'),
                             mox.StrContains('testdata/foo'))
    self.mox.ReplayAll()

    self.assertRaises(IOError,
                      cap_crawl.FetchUrl, 'testdata/foo')

  def testFetchUrl_external(self):
    url = 'http://whatever'
    content = 'foo'
    response = self.mox.CreateMockAnything()
    response.content = content
    cap_crawl.urlfetch.fetch(
        url, deadline=cap_crawl.URLFETCH_DEADLINE_SECS).AndReturn(response)
    self.mox.ReplayAll()

    self.assertEquals(cap_crawl.FetchUrl(url), content)


class GetCapTest(CapCrawlTestBase):
  """Tests for cap_crawl.GetCap."""

  def setUp(self):
    super(GetCapTest, self).setUp()
    self.mox.StubOutWithMock(cap_crawl, 'FetchUrl')
    self.mox.StubOutWithMock(cap_crawl.cap_parse_mem, 'MemoryCapParser')
    self.mox.StubOutWithMock(cap_crawl.cap_parse_db, 'MakeDbAlertFromMem')
    self.mox.StubOutWithMock(cap_crawl.xml_util, 'ParseText')

  def testGetCap_nominal(self):
    cap_url = 'http://this.is.a.cap'
    cap_str = '<alert/>'
    cap_text = db.Text(cap_str)
    cap_crawl.FetchUrl(cap_url).AndReturn(cap_str)
    cap_crawl.xml_util.ParseText(cap_str).AndReturn(cap_text)
    parser = self.mox.CreateMock(cap_parse_mem.CapParser)
    cap_crawl.cap_parse_mem.MemoryCapParser().AndReturn(parser)
    alert_mem = self.mox.CreateMockAnything()
    parse_errors = ['foo', 'bar']
    parser.MakeAlert(mox.IgnoreArg(), cap_text).AndReturn(
        (alert_mem, parse_errors))
    alert_db = cap_schema.CapAlert()
    cap_crawl.cap_parse_db.MakeDbAlertFromMem(alert_mem).AndReturn(alert_db)
    cap_crawl.xml_util.ParseText('foo').AndReturn(db.Text('foo'))
    cap_crawl.xml_util.ParseText('bar').AndReturn(db.Text('bar'))
    self.mox.ReplayAll()

    feed = cap_schema.Feed()
    feed.put()
    crawl = cap_schema.Crawl()
    crawl.put()
    actual_alert_db = cap_crawl.GetCap(feed, crawl, cap_url)
    self.assertTrue(actual_alert_db is alert_db)
    self.assertTrue(actual_alert_db.crawl is crawl)
    self.assertTrue(actual_alert_db.feed is feed)
    self.assertEquals(actual_alert_db.url, cap_url)
    self.assertEquals(actual_alert_db.text, cap_text)
    self.assertListEqual(actual_alert_db.parse_errors, parse_errors)


class GetFeedIndexTest(CapCrawlTestBase):
  """Tests for cap_crawl.GetFeedIndex."""

  def setUp(self):
    super(GetFeedIndexTest, self).setUp()
    self.mox.StubOutWithMock(cap_crawl, 'FetchUrl')
    self.mox.StubOutWithMock(cap_index_parse, 'ParseCapIndex')

  def testGetFeedIndex(self):
    feed_url = 'http://some.feed'
    index_text = '<atom/>'
    cap_crawl.FetchUrl(feed_url).AndReturn(index_text)
    parsed_index = object()
    cap_index_parse.ParseCapIndex(index_text).AndReturn(parsed_index)
    self.mox.ReplayAll()

    self.assertTrue(cap_crawl.GetFeedIndex(feed_url) is parsed_index)


class CrawlControllerTestBase(CapCrawlTestBase):
  """Base class for tests for cap_crawl.CrawlController* classes.

  Attributes:
    crawl: cap_schema.Crawl object
    master: cap_crawl.CrawlControllerMaster object
  """

  def setUp(self):
    super(CrawlControllerTestBase, self).setUp()
    self.crawl = cap_schema.Crawl()
    self.crawl.put()
    self.now = fake_clock.FakeNow()
    self.master = cap_crawl.CrawlControllerMaster(
        _crawl=self.crawl, _now=self.now)

  def _NewShards(self, num_shards, crawl=None):
    """Generates shard objects for testing.

    Args:
      num_shards: Number of shards to create (int).
      crawl: cap_schema.Crawl to reference, or None to use self.crawl.

    Returns:
      List containing num_shards cap_schema.CrawlShard objects.
    """
    if not crawl:
      crawl = self.crawl
    return cap_test_util.NewShards(num_shards, crawl)

  def _NewShard(self, url, crawl=None, feed=None):
    """Generates a shard object for testing.

    Args:
      url: URL for the shard (str)
      crawl: cap_schema.Crawl to reference, or None to use self.crawl.
      feed: cap_schema.Feed to reference, or None to leave it unreferenced.

    Returns:
      cap_schema.CrawlShard object, already saved.
    """
    if not crawl:
      crawl = self.crawl

    return cap_test_util.NewShard(url, crawl, feed=feed)


class CrawlControllerWorkerDoShardTest(CrawlControllerTestBase):
  """Tests for cap_crawl.CrawlControllerWorker.DoShard."""

  def setUp(self):
    super(CrawlControllerWorkerDoShardTest, self).setUp()
    self.mox.StubOutWithMock(cap_crawl, 'GetCap')
    self.mox.StubOutWithMock(cap_crawl, 'GetFeedIndex')

    self.feed = cap_schema.Feed()
    self.feed.put()
    self.url = 'http://foo'
    self.shard = self._NewShard(self.url, feed=self.feed)
    self.worker = cap_crawl.CrawlControllerWorker(
        str(self.shard.key()), _now=self.now)

  def testInit_findsShard(self):
    self.assertTrue(self.worker.GetShard())

  def testDoShard_cap(self):
    shard = self.worker.GetShard()
    started = self.now.now
    cap = cap_schema.CapAlert()
    parse_errors = [db.Text(x) for x in ['some error', 'some other error']]
    cap.parse_errors = parse_errors
    cap_crawl.GetCap(shard.feed, shard.crawl, self.url).AndReturn(cap)
    cap_crawl.logging.debug('Created CAP for %r', self.url)
    self.mox.ReplayAll()

    self.worker.DoShard()
    self.assertEquals(shard.started, started)
    self.assertListEqual(shard.parse_errors, parse_errors)
    self.assertTrue(shard.is_done)
    self.assertEquals(shard.finished, started + self.now.increment)

  def testDoShard_GetCapRaisesDeadlineExceeded(self):
    shard = self.worker.GetShard()
    started = self.now.now
    cap_crawl.GetCap(shard.feed, shard.crawl, self.url).AndRaise(
        DeadlineExceededError)
    self.mox.ReplayAll()

    self.assertRaises(DeadlineExceededError, self.worker.DoShard)
    self.assertEquals(shard.started, started)

  def testDoShard_GetCapRaisesException(self):
    shard = self.worker.GetShard()
    started = self.now.now
    cap_crawl.GetCap(shard.feed, shard.crawl, self.url).AndRaise(
        ValueError('foobar'))
    cap_crawl.logging.error(
        'Skipping URL %r: %r', self.url, mox.IsA(ValueError))
    self.mox.ReplayAll()

    self.worker.DoShard()
    self.assertEquals(shard.started, started)
    self.assertListEqual(shard.parse_errors, [])
    self.assertTrue(shard.is_done)
    self.assertEquals(shard.finished, started + self.now.increment)

    # Check that the error message contains key information.
    self.assertIn('Skipping URL', shard.error)
    self.assertIn(self.url, shard.error)
    self.assertIn('ValueError', shard.error)
    self.assertIn('foobar', shard.error)

  def testDoShard_capIndex(self):
    shard = self.worker.GetShard()
    started = self.now.now
    cap_crawl.GetCap(shard.feed, shard.crawl, self.url).AndRaise(
        cap_parse_mem.NotCapError('foo'))
    cap_crawl.logging.debug('Not CAP ... assuming CAP index: %r', self.url)
    num_urls = 3
    urls = ['http://url%d' % x for x in xrange(num_urls)]
    cap_crawl.GetFeedIndex(self.url).AndReturn(urls)
    cap_crawl.logging.debug('Found %d URLs in nested index', num_urls)
    for i in xrange(num_urls):
      cap_crawl._EnqueuePush(shard.crawl, shard.feed, urls[i])
    self.mox.ReplayAll()

    self.worker.DoShard()
    self.assertEquals(shard.started, started)
    self.assertListEqual(shard.parse_errors, [])
    self.assertTrue(shard.is_done)
    self.assertEquals(shard.finished, started + self.now.increment)


class MaybePushShardUnsafeTest(CrawlControllerTestBase):
  """Tests for cap_crawl._MaybePushShardUnsafe."""

  def setUp(self):
    super(MaybePushShardUnsafeTest, self).setUp()
    self.feed = cap_schema.Feed()
    self.feed.put()
    self.crawl_started = datetime.datetime(2009, 9, 1, 2, 3, 4)
    self.crawl.started = self.crawl_started
    self.url = 'http://foo'

  def testMaybePushShardUnsafe_new(self):
    cap_crawl.logging.debug('MaybePushShard %r', self.url)
    self.mox.ReplayAll()

    shard, is_new = cap_crawl._MaybePushShardUnsafe(self.crawl, self.feed, self.url)
    self.assertEquals(shard.feed.key(), self.feed.key())
    self.assertEquals(shard.url, self.url)
    self.assertEquals(shard.crawl.key(), self.crawl.key())
    self.assertEquals(shard.key().name(),
                      'CrawlShard %s %s' % (self.crawl_started, self.url))
    self.assertTrue(is_new)

  def testMaybePushShardUnsafe_existing(self):
    cap_crawl.logging.debug('MaybePushShard %r', self.url)
    cap_crawl.logging.debug('MaybePushShard %r', self.url)
    self.mox.ReplayAll()

    cap_crawl._MaybePushShardUnsafe(self.crawl, self.feed, self.url)
    # Second call should retrieve the existing shard.
    shard, is_new = cap_crawl._MaybePushShardUnsafe(
        self.crawl, self.feed, self.url)
    self.assertEquals(shard.feed.key(), self.feed.key())
    self.assertEquals(shard.url, self.url)
    self.assertEquals(shard.crawl.key(), self.crawl.key())
    self.assertEquals(shard.key().name(),
                      'CrawlShard %s %s' % (self.crawl_started, self.url))
    self.assertFalse(is_new)


class MaybePushShardTest(CrawlControllerTestBase):
  """Tests for cap_crawl._MaybePushShard."""

  def setUp(self):
    super(MaybePushShardTest, self).setUp()
    self.mox.StubOutWithMock(cap_crawl, '_MaybePushShardUnsafe')
    self.feed = cap_schema.Feed()
    self.url = 'http://foo'
    self.shard = cap_schema.CrawlShard()
    self.shard.put()

  def testMaybePushShard_new(self):
    cap_crawl._MaybePushShardUnsafe(
        self.crawl, self.feed, self.url).AndReturn((self.shard, True))
    cap_crawl._EnqueueShard(str(self.shard.key()))
    self.mox.ReplayAll()

    shard, is_new = cap_crawl._MaybePushShard(self.crawl, self.feed, self.url)
    self.assertEquals(shard, self.shard)
    self.assertTrue(is_new)

  def testMaybePushShard_existing(self):
    cap_crawl._MaybePushShardUnsafe(
        self.crawl, self.feed, self.url).AndReturn((self.shard, False))
    self.mox.ReplayAll()

    shard, is_new = cap_crawl._MaybePushShard(self.crawl, self.feed, self.url)
    self.assertEquals(shard, self.shard)
    self.assertFalse(is_new)


class CrawlControllerMasterTest(CrawlControllerTestBase):
  """Tests for cap_crawl.CrawlControllerMaster methods."""

  def testGetCrawl(self):
    self.assertTrue(self.master.GetCrawl() is self.crawl)

  def testCrawlInProgress_mostRecentInProgress(self):
    # Create some old, finished crawls.
    for i in xrange(3):
      day = i + 1
      started = datetime.datetime(2009, 9, day)
      finished = started + datetime.timedelta(minutes=5)
      crawl = cap_schema.Crawl(
          is_done=True, started=started, fininshed=finished)
      crawl.put()

    # Make the common crawl the most recent
    started += datetime.timedelta(days=1)
    self.crawl.started = started
    self.crawl.is_done = False
    self.crawl.put()

    cap_crawl.logging.debug('Found crawl in progress (started %s)', started)
    self.mox.ReplayAll()

    crawl_in_progress = self.master._CrawlInProgress()
    self.assertEquals(crawl_in_progress.key(), self.crawl.key())

  def testCrawlInProgress_noneInProgress(self):
    self.crawl.is_done = True
    self.crawl.put()

    self.mox.ReplayAll()

    self.assertEquals(self.master._CrawlInProgress(), None)

  def testAreMoreShardsInProgress_true(self):
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster,
                             '_QueryAnyIncompleteShard')
    self.master._QueryAnyIncompleteShard().AndReturn(cap_schema.CrawlShard())
    self.mox.ReplayAll()

    self.assertTrue(self.master._AreMoreShardsInProgress())

  def testAreMoreShardsInProgress_false(self):
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster,
                             '_QueryAnyIncompleteShard')
    self.master._QueryAnyIncompleteShard().AndReturn(None)
    self.mox.ReplayAll()

    self.assertFalse(self.master._AreMoreShardsInProgress())

  def testQueryAnyIncompleteShard_returnsShard(self):
    # Write some shards for this crawl.
    shards = self._NewShards(7)
    shard_keys = frozenset([shard.key() for shard in shards])
    self.assertEquals(len(shard_keys), 7)

    # Write some shards for another crawl.
    crawl = cap_schema.Crawl()
    crawl.put()
    self._NewShards(13, crawl=crawl)

    # See that we get one of the ones we expect.
    self.assertIn(self.master._QueryAnyIncompleteShard(), shard_keys)

  def testQueryAnyIncompleteShard_returnsNone(self):
    # Add some shards, but make them all done.
    shards = self._NewShards(7)
    for shard in shards:
      shard.is_done = True
      shard.put()

    self.assertEquals(self.master._QueryAnyIncompleteShard(), None)

  def testEnsureCrawl_inProgress(self):
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster,
                             '_CrawlInProgress')
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster,
                             '_AreMoreShardsInProgress')
    crawl = object()
    self.master._CrawlInProgress().AndReturn(crawl)
    self.master._AreMoreShardsInProgress().AndReturn(True)
    cap_crawl.logging.debug('Waiting for other workers')
    self.mox.ReplayAll()

    self.master._EnsureCrawl()
    self.assertTrue(self.master.GetCrawl(), crawl)

  def testEnsureCrawl_crawlIsDone(self):
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster,
                             '_CrawlInProgress')
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster,
                             '_AreMoreShardsInProgress')
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster,
                             '_CrawlIsDone')
    crawl = object()
    self.master._CrawlInProgress().AndReturn(crawl)
    self.master._AreMoreShardsInProgress().AndReturn(False)
    self.master._CrawlIsDone()
    self.mox.ReplayAll()

    self.master._EnsureCrawl()
    self.assertTrue(self.master.GetCrawl(), crawl)

  def testEnsureCrawl_newCrawl(self):
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster,
                             '_CrawlInProgress')
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster, '_NewCrawl')
    self.master._CrawlInProgress().AndReturn(None)
    self.master._NewCrawl()
    self.mox.ReplayAll()

    self.master._EnsureCrawl()
    # We rely on _NewCrawl to set the crawl, so since we mocked it, it should
    # not be set.
    self.assertTrue(self.master.GetCrawl() is None)

  def testCrawlIsDone(self):
    crawl_finished = self.now.now
    # Create feeds, some which are crawled and some which are not.
    num_feeds = 5
    feeds = cap_test_util.NewFeeds(num_feeds)
    feed_urls = frozenset([feed.url for feed in feeds])
    feed_urls_crawled = frozenset([feed.url for feed in feeds[:3]])
    feed_urls_not_crawled = frozenset([feed.url for feed in feeds[3:]])
    # Put the feeds that we crawled into the crawl record.
    crawl = self.crawl
    for feed_url in feed_urls_crawled:
      crawl.feed_urls.append(feed_url)
    crawl.put()

    cap_crawl.logging.debug('Crawl is done')
    self.mox.ReplayAll()

    self.master._CrawlIsDone()
    self.assertTrue(crawl.is_done)
    self.assertEquals(crawl.finished, crawl_finished)

    # See that the right feeds were updated.
    actual_feed_urls = []
    for feed in cap_schema.Feed.all():
      actual_feed_urls.append(feed.url)
      if feed.url in feed_urls_crawled:
        self.assertEquals(feed.last_crawl.key(), self.crawl.key())
      else:
        self.assertFalse(feed.last_crawl)
    self.assertSameElements(actual_feed_urls, feed_urls)

  def testNewCrawl_noFeeds(self):
    self.master._crawl = object()
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster, '_GetFeeds')
    crawl_started = self.now.now
    self.master._GetFeeds(crawl_started).AndReturn(None)
    cap_crawl.logging.debug('No feeds to crawl')
    self.mox.ReplayAll()

    self.master._NewCrawl()
    self.assertTrue(self.master.GetCrawl() is None)

  def testNewCrawl_someFeeds(self):
    self.master._crawl = object()
    self.mox.StubOutWithMock(cap_crawl.CrawlControllerMaster, '_GetFeeds')
    crawl_started = self.now.now

    num_feeds = 3
    feeds = cap_test_util.NewFeeds(num_feeds)
    self.master._GetFeeds(crawl_started).AndReturn(feeds)
    cap_crawl.logging.debug('Started new crawl at %s', crawl_started)
    for feed in feeds:
      cap_crawl._EnqueuePush(mox.IgnoreArg(), feed, feed.url)
    self.mox.ReplayAll()

    self.master._NewCrawl()
    crawl = self.master.GetCrawl()
    self.assertTrue(crawl.is_saved())
    self.assertEquals(crawl.started, crawl_started)
    self.assertListEqual(crawl.feed_urls, [feed.url for feed in feeds])


class CrawlControllerMasterGetFeedsTest(CrawlControllerTestBase):
  """Tests for cap_crawl.CrawlControllerMaster._GetFeeds.

  Attributes:
    crawl_started: Timestamp at which _GetFeeds is executed, representing the
        start time of the potential crawl (noon).
    all_feed_urls: URL's of all test data feeds.
    uncrawlable_feed_url: URL of an uncrawlable feed.
    nonroot_feed_url: URL of a feed marked non-root (is_root=False)
    old_crawl_feed_url: URL of a feed that was crawled beyond the default
        crawl interval (8am).
    recent_crawl_feed_url: URL of a feed that was crawled within the default
        crawl interval (11:30am).
    recent_fast_crawl_feed_url: URL of a feed that was crawled within the
        default crawl interval (11:30am), but which has a short crawl period
        (5 min).
    never_crawled_feed_url: URL of a feed that has never been crawled.
    deleted_crawl_feed_url: URL of a feed that has a broken reference to a
        Crawl.
    actual_feed_urls: Set of feed URL's returned by _GetFeeds.
  """

  def setUp(self):
    super(CrawlControllerMasterGetFeedsTest, self).setUp()
    # This is when we will start this crawl (noon)
    self.crawl_started = datetime.datetime(2009, 9, 1, 12, 0)
    num_feeds = 10
    feeds = cap_test_util.NewFeeds(num_feeds)
    self.all_feed_urls = [feed.url for feed in feeds]

    # Make sure the defaults are what we think they are.
    for feed in feeds:
      self.assertTrue(feed.is_crawlable)
      self.assertTrue(feed.is_root)

    # Test an uncrawlable feed.
    feed = feeds.pop(0)
    feed.is_crawlable = False
    feed.put()
    self.uncrawlable_feed_url = feed.url

    # Test a non-root feed.
    feed = feeds.pop(0)
    feed.is_root = False
    feed.put()
    self.nonroot_feed_url = feed.url

    # Set up an old crawl (8am).
    old_crawl = cap_schema.Crawl(started=datetime.datetime(2009, 9, 1, 8),
                                 finished=datetime.datetime(2009, 9, 1, 8, 5),
                                 is_done=True)
    old_crawl.put()

    # Set up a recent crawl (11:30am).
    recent_crawl = cap_schema.Crawl(
        started=datetime.datetime(2009, 9, 1, 11, 30),
        finished=datetime.datetime(2009, 9, 1, 11, 35), is_done=True)
    recent_crawl.put()

    # Set up an old crawl (7am) that we will delete after we reference it.
    deleted_crawl = cap_schema.Crawl(
        started=datetime.datetime(2009, 9, 1, 7),
        finished=datetime.datetime(2009, 9, 1, 7, 5), is_done=True)
    deleted_crawl.put()

    # Make sure the old crawl happened before the default crawl interval.
    self.assertTrue(self.crawl_started - old_crawl.finished
                    > cap_schema.DEFAULT_CRAWL_PERIOD)

    # Make sure the recent crawl happened during the default crawl interval.
    self.assertTrue(self.crawl_started - recent_crawl.finished
                    < cap_schema.DEFAULT_CRAWL_PERIOD)

    # Test a feed that we crawled a long time ago.
    feed = feeds.pop(0)
    feed.last_crawl = old_crawl
    feed.put()
    self.old_crawl_feed_url = feed.url

    # Test a feed that we crawled recently.
    feed = feeds.pop(0)
    feed.last_crawl = recent_crawl
    feed.put()
    self.recent_crawl_feed_url = feed.url

    # Test a feed that we crawled recently, but which has a short crawl period.
    feed = feeds.pop(0)
    feed.last_crawl = recent_crawl
    feed.crawl_period_in_minutes = 5
    feed.put()
    self.recent_fast_crawl_feed_url = feed.url

    # Test a feed that has never been crawled.
    feed = feeds.pop(0)
    self.never_crawled_feed_url = feed.url

    # Test a feed whose crawl has been deleted.
    feed = feeds.pop(0)
    feed.last_crawl = deleted_crawl
    feed.put()
    self.deleted_crawl_feed_url = feed.url

    # Delete the crawl that we had planned to delete.
    deleted_crawl.delete()

    # Get the feed URL's.
    self.actual_feed_urls = [
        feed.url for feed in self.master._GetFeeds(self.crawl_started)]

  def testGetFeeds_excludesUncrawlableFeeds(self):
    self.assertNotIn(self.uncrawlable_feed_url, self.actual_feed_urls)

  def testGetFeeds_excludesNonRootFeeds(self):
    self.assertNotIn(self.nonroot_feed_url, self.actual_feed_urls)

  def testGetFeeds_includesOldCrawlFeeds(self):
    self.assertIn(self.old_crawl_feed_url, self.actual_feed_urls)

  def testGetFeeds_excludesRecentCrawlFeeds(self):
    self.assertNotIn(self.recent_crawl_feed_url, self.actual_feed_urls)

  def testGetFeeds_includesRecentFastCrawlFeeds(self):
    self.assertIn(self.recent_fast_crawl_feed_url, self.actual_feed_urls)

  def testGetFeeds_includesNeverCrawledFeeds(self):
    self.assertIn(self.never_crawled_feed_url, self.actual_feed_urls)

  def testGetFeeds_includesDeletedCrawlFeeds(self):
    self.assertIn(self.deleted_crawl_feed_url, self.actual_feed_urls)


class CrawlNudgeTest(CapCrawlTestBase):
  """Tests for cap_crawl.CrawlNudge."""

  def setUp(self):
    super(CrawlNudgeTest, self).setUp()
    self.mox.StubOutWithMock(cap_crawl, 'CrawlControllerMaster')
    self.controller = self.mox.CreateMock(cap_crawl.CrawlControllerMaster)

  def testCrawlNudge(self):
    cap_crawl.CrawlControllerMaster(_now=datetime.datetime.now).AndReturn(
        self.controller)
    self.mox.ReplayAll()

    actual_controller = cap_crawl.CrawlNudge()
    self.assertTrue(actual_controller is self.controller)


class CrawlWorkerTest(CapCrawlTestBase):
  """Tests for cap_crawl.CrawlWorker."""

  def setUp(self):
    super(CrawlWorkerTest, self).setUp()
    self.mox.StubOutWithMock(cap_crawl, 'CrawlControllerWorker')
    self.controller = self.mox.CreateMock(cap_crawl.CrawlControllerWorker)

  def testCrawlWorker(self):
    shard_key = 'foo'
    cap_crawl.CrawlControllerWorker(
        shard_key, _now=datetime.datetime.now).AndReturn(self.controller)
    self.controller.DoShard()
    self.mox.ReplayAll()

    actual_controller = cap_crawl.CrawlWorker(shard_key)
    self.assertTrue(actual_controller is self.controller)


# TODO(Matt Frantz): Write tests for the webapp.RequestHandler subclasses.


def main(unused_argv):
  googletest.main()


if __name__ == '__main__':
  app.run()
