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

"""Unit tests for cap_mirror."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import datetime
import StringIO

import google3
import mox

from google3.apphosting.ext import db
from google3.apphosting.ext import webapp
from google3.apphosting.runtime.apiproxy_errors import DeadlineExceededError
from google3.pyglib import app
from google3.pyglib import resources
from google3.testing.pybase import googletest

from google3.dotorg.gongo.appengine_cap2kml import cap_mirror
from google3.dotorg.gongo.appengine_cap2kml import cap_schema
from google3.dotorg.gongo.appengine_cap2kml import cap_test_util
from google3.dotorg.gongo.appengine_cap2kml import db_test_util
from google3.dotorg.gongo.appengine_cap2kml import fake_clock
from google3.dotorg.gongo.appengine_cap2kml import mox_util
from google3.dotorg.gongo.appengine_cap2kml import users_test_util


class CapMirrorTestBase(mox.MoxTestBase, db_test_util.DbTestBase,
                        users_test_util.UsersTestBase):
  """Base class for all cap_mirror unit tests."""

  def setUp(self):
    super(CapMirrorTestBase, self).setUp()
    # Stub out anything that we never want to call for real.
    self.mox.StubOutWithMock(cap_mirror, 'logging')


class DefaultFeedsTest(CapMirrorTestBase):
  """Tests for cap_mirror.DefaultFeeds."""

  def testDefaultFeeds_internal(self):
    feeds = cap_mirror.DefaultFeeds('internal')
    feed_urls = frozenset([feed.url for feed in feeds])
    self.assertIn('testdata/rss_feed1.xml', feed_urls)
    self.assertIn('_FAKE_FEED_URL_1_', feed_urls)

  def testDefaultFeeds_external(self):
    feeds = cap_mirror.DefaultFeeds('external')
    feed_urls = frozenset([feed.url for feed in feeds])
    self.assertIn('http://www.weather.gov/alerts-beta/us.php?x=0', feed_urls)


class DeleteInBatchesTest(CapMirrorTestBase):
  """Tests for cap_mirror.DeleteInBatches."""

  def setUp(self):
    super(DeleteInBatchesTest, self).setUp()
    self.mox.StubOutWithMock(cap_mirror, 'db')

  def testDeleteInBatches_oneBatch(self):
    models = [1, 2, 3]
    batch_size = 50
    query = self.mox.CreateMockAnything()
    query_factory = lambda: query
    query.fetch(batch_size).AndReturn(models)
    cap_mirror.db.delete(models)
    query.fetch(batch_size).AndReturn([])
    self.mox.ReplayAll()

    cap_mirror.DeleteInBatches(query_factory, batch_size=batch_size)

  def testDeleteInBatches_threeBatches(self):
    batch_size = 50

    def NewMockQuery(models_to_return):
      query = self.mox.CreateMockAnything()
      query.fetch(batch_size).AndReturn(models_to_return)
      return query

    query_factory = self.mox.CreateMockAnything()
    models = [1, 2, 3]
    query_factory().AndReturn(NewMockQuery(models))
    cap_mirror.db.delete(models)
    query_factory().AndReturn(NewMockQuery(models))
    cap_mirror.db.delete(models)
    query_factory().AndReturn(NewMockQuery(models))
    cap_mirror.db.delete(models)
    query_factory().AndReturn(NewMockQuery([]))
    self.mox.ReplayAll()

    cap_mirror.DeleteInBatches(query_factory, batch_size=batch_size)


class SaveFeedTest(CapMirrorTestBase):
  """Tests for cap_mirror.SaveFeed."""

  def setUp(self):
    super(SaveFeedTest, self).setUp()
    num_feeds = 3
    self.feeds = cap_test_util.NewFeeds(num_feeds)
    self.feed_keys = frozenset([feed.key() for feed in self.feeds])

    # Prepare for a single call to SaveFeed from each test.
    cap_mirror.logging.info(mox.StrContains('Saving Feed'), mox.IgnoreArg())

  def testSaveFeed_invalidKey(self):
    key = 'foo'
    # It doesn't matter what we pass if the key is wrong.
    is_crawlable = object()
    is_root = object()
    crawl_period = object()

    self.mox.ReplayAll()

    self.assertRaisesWithRegexpMatch(
        cap_mirror.SaveFeedError, 'Invalid Feed key',
        cap_mirror.SaveFeed, key, is_crawlable, is_root, crawl_period)

  def testSaveFeed_noFeedFound(self):
    feed = self.feeds.pop(0)
    key = str(feed.key())
    feed.delete()
    # It doesn't matter what we pass if the key is wrong.
    is_crawlable = object()
    is_root = object()
    crawl_period = object()

    self.mox.ReplayAll()

    self.assertRaisesWithRegexpMatch(
        cap_mirror.SaveFeedError, 'No Feed found matching key',
        cap_mirror.SaveFeed, key, is_crawlable, is_root, crawl_period)

  def testSaveFeed_multipleFeeds(self):
    key = str(self.feeds[0].key())
    # It doesn't matter what we pass if the key is wrong.
    is_crawlable = object()
    is_root = object()
    crawl_period = object()

    # Multiple feeds with a single key represents Datastore corruption, so we
    # have to fake it.
    self.mox.StubOutWithMock(cap_schema, 'Feed')
    cap_schema.Feed.gql(
        mox.StrContains('WHERE'), db.Key(key)).AndReturn(xrange(2))
    self.mox.ReplayAll()

    self.assertRaisesWithRegexpMatch(
        cap_mirror.SaveFeedError, 'Multiple Feeds match key',
        cap_mirror.SaveFeed, key, is_crawlable, is_root, crawl_period)

  def testSaveFeed_changeEverything(self):
    feed = self.feeds[0]
    key = feed.key()
    is_crawlable = not feed.is_crawlable
    is_root = not feed.is_root
    crawl_period_in_minutes = 2 * feed.crawl_period_in_minutes

    cap_mirror.logging.info(mox.StrContains('Saving Feed'), mox.IgnoreArg())
    self.mox.ReplayAll()

    cap_mirror.SaveFeed(str(key), is_crawlable, is_root, crawl_period_in_minutes)
    new_feed = cap_test_util.GetFeed(key)
    self.assertEquals(is_crawlable, new_feed.is_crawlable)
    self.assertEquals(is_root, new_feed.is_root)
    self.assertEquals(crawl_period_in_minutes, new_feed.crawl_period_in_minutes)

  def testSaveFeed_negativeCrawlPeriod(self):
    feed = self.feeds[0]
    key = feed.key()
    is_crawlable = not feed.is_crawlable
    is_root = not feed.is_root
    crawl_period_in_minutes = -1

    cap_mirror.logging.info(mox.StrContains('Saving Feed'), mox.IgnoreArg())
    self.mox.ReplayAll()

    cap_mirror.SaveFeed(str(key), is_crawlable, is_root, crawl_period_in_minutes)
    new_feed = cap_test_util.GetFeed(key)
    self.assertEquals(is_crawlable, new_feed.is_crawlable)
    self.assertEquals(is_root, new_feed.is_root)
    self.assertEquals(feed.crawl_period_in_minutes, new_feed.crawl_period_in_minutes)


class ClearFeedsTest(CapMirrorTestBase):
  """Tests for cap_mirror.ClearFeeds."""

  def testClearFeeds_nominal(self):
    num_feeds = 3
    feeds = cap_test_util.NewFeeds(num_feeds)

    cap_mirror.ClearFeeds()
    self.assertListEqual([], list(cap_schema.Feed.all()))


class ResetFeedsTest(CapMirrorTestBase):
  """Tests for cap_mirror.ResetFeeds."""

  @staticmethod
  def _AllFeedKeys():
    """Returns all Feed keys in the Datastore.

    Returns:
      Set of key objects (frozenset of db.Key)
    """
    return frozenset(db.GqlQuery('SELECT __key__ FROM Feed'))

  def testResetFeeds_internal(self):
    feed_list = 'internal'
    cap_mirror.ResetFeeds(feed_list)
    self.assertSameElements(cap_mirror.FEED_LISTS[feed_list],
                            [feed.url for feed in cap_schema.Feed.all()])

  def testResetFeeds_doesntClobberExistingFeeds(self):
    old_feeds = cap_test_util.NewFeeds(5)
    old_feed_urls = [feed.url for feed in old_feeds]
    feed_list = 'internal'
    cap_mirror.ResetFeeds(feed_list)
    self.assertSameElements(cap_mirror.FEED_LISTS[feed_list] + old_feed_urls,
                            [feed.url for feed in cap_schema.Feed.all()])

  def testResetFeeds_idempotent(self):
    feed_list = 'internal'
    cap_mirror.ResetFeeds(feed_list)
    feed_keys = self._AllFeedKeys()
    cap_mirror.ResetFeeds(feed_list)
    self.assertSameElements(feed_keys, self._AllFeedKeys())

  def testResetFeeds_preservesDefaultKeys(self):
    # We want ResetFeeds to be stable with respect to previous versions of
    # itself.  In previous versions, Feed models were instantiated without
    # specifying the key.
    feed_list = 'internal'
    for url in cap_mirror.FEED_LISTS[feed_list]:
      feed = cap_schema.Feed()
      feed.url = url
      feed.put()

    feed_keys = self._AllFeedKeys()
    cap_mirror.ResetFeeds(feed_list)
    self.assertSameElements(feed_keys, self._AllFeedKeys())


class GetCrawlFromRequestTest(CapMirrorTestBase):
  """Tests for cap_mirror._GetCrawlFromRequest."""

  def setUp(self):
    super(GetCrawlFromRequestTest, self).setUp()
    num_crawls = 5
    self.now = fake_clock.FakeNow()
    self.crawls = cap_test_util.NewCrawls(num_crawls, self.now)
    self.handler = self.mox.CreateMock(webapp.RequestHandler)
    self.handler.request = self.mox.CreateMock(webapp.Request)
    self.handler.response = self.mox.CreateMock(webapp.Response)
    self.handler.response.out = StringIO.StringIO()
    self.mox.StubOutWithMock(cap_mirror, '_MostRecentCrawl')

  def testGetCrawlFromRequest_validCrawlInRequest(self):
    crawl = self.crawls[3]
    self.handler.request.get('crawl').AndReturn(str(crawl.key()))

    self.mox.ReplayAll()

    actual_crawl = cap_mirror._GetCrawlFromRequest(self.handler)
    self.assertEquals(actual_crawl.key(), crawl.key())

  def testGetCrawlFromRequest_mostRecentCrawl(self):
    crawl = self.crawls[1]
    self.handler.request.get('crawl').AndReturn(None)
    cap_mirror._MostRecentCrawl().AndReturn(crawl.key())

    self.mox.ReplayAll()

    actual_crawl = cap_mirror._GetCrawlFromRequest(self.handler)
    self.assertEquals(actual_crawl.key(), crawl.key())

  def testGetCrawlFromRequest_noCrawls(self):
    self.handler.request.get('crawl').AndReturn(None)
    cap_mirror._MostRecentCrawl().AndReturn(None)
    cap_mirror.logging.exception(mox_util.AsStrContains('No crawls'))

    self.mox.ReplayAll()

    self.assertTrue(cap_mirror._GetCrawlFromRequest(self.handler) is None)

  def testGetCrawlFromRequest_unknownKey(self):
    crawl = self.crawls[0]
    crawl_key = crawl.key()
    crawl.delete()
    self.handler.request.get('crawl').AndReturn(str(crawl_key))
    cap_mirror.logging.exception(mox_util.AsStrContains('Unknown Crawl key'))

    self.mox.ReplayAll()

    self.assertTrue(cap_mirror._GetCrawlFromRequest(self.handler) is None)


class MostRecentCrawlTest(CapMirrorTestBase):
  """Tests for cap_mirror._MostRecentCrawl."""

  def testMostRecentCrawl_nominal(self):
    num_crawls = 5
    now = fake_clock.FakeNow()
    crawls = cap_test_util.NewCrawls(num_crawls, now)
    expected_crawl = crawls[-1]

    self.mox.ReplayAll()

    actual_crawl_key = cap_mirror._MostRecentCrawl()
    self.assertEquals(expected_crawl.key(), actual_crawl_key)

  def testMostRecentCrawl_noCrawls(self):
    self.mox.ReplayAll()
    self.assertTrue(cap_mirror._MostRecentCrawl() is None)


class ClearCrawlsTest(CapMirrorTestBase):
  """Tests for cap_mirror.ClearCrawls."""

  def testClearCrawls_nominal(self):
    num_crawls = 3
    now = fake_clock.FakeNow()
    crawls = cap_test_util.NewCrawls(num_crawls, now)
    for crawl in crawls:
      num_shards = 4
      cap_test_util.NewShards(num_shards, crawl)

    cap_mirror.logging.info(mox.StrContains('Deleting crawl shards'))
    cap_mirror.logging.info(mox.StrContains('Deleting crawls'))
    self.mox.ReplayAll()

    batch_size = 2
    cap_mirror.ClearCrawls(batch_size)
    self.assertListEqual([], list(cap_schema.Crawl.all()))
    self.assertListEqual([], list(cap_schema.CrawlShard.all()))


class PurgeCrawlsTest(CapMirrorTestBase):
  """Tests for cap_mirror.PurgeCrawls."""

  def setUp(self):
    super(PurgeCrawlsTest, self).setUp()
    self.now = fake_clock.FakeNow(initial_value=datetime.datetime(2009, 9, 11))
    # Nominal parameters for the PurgeCrawls call.
    self.days_to_keep = 7
    self.batch_size = 10
    self.cutoff_date = datetime.datetime(2009, 9, 4)

  def _MakeSomeCrawls(self):
    """Generates test Crawls in the Datastore.

    Returns:
      (crawls_before, crawls_after)
      crawls_before: List of cap_schema.Crawl objects that happened before
          self.cutoff_date.
      crawls_after: List of cap_schema.Crawl objects that happened after
          self.cutoff_date.
    """
    num_crawls = 3
    now = fake_clock.FakeNow(initial_value=self.cutoff_date -
                             datetime.timedelta(days=30))
    crawls_before = cap_test_util.NewCrawls(num_crawls, now)
    now.now = self.cutoff_date + datetime.timedelta(days=1)
    crawls_after = cap_test_util.NewCrawls(num_crawls, now)
    return crawls_before, crawls_after

  def _PurgeCrawl(self, key, unused_batch_size):
    """Removes the specified Crawl from the Datastore.

    Args:
      key: db.Key representing the Crawl.
      unused_batch_size: Included for compatibility with cap_mirror.PurgeCrawl.
    """
    db.delete(cap_schema.Crawl.gql('WHERE __key__ = :1', key))

  def testPurgeCrawls_noCrawls(self):
    self.mox.StubOutWithMock(cap_mirror, 'PurgeCrawl')
    cap_mirror.logging.info(mox.StrContains('Purging crawls'), self.cutoff_date)
    cap_mirror.logging.info(mox.StrContains('No more crawls'))
    self.mox.ReplayAll()

    last_crawls = frozenset()
    crawls_purged, error = cap_mirror.PurgeCrawls(
        self.days_to_keep, self.batch_size, last_crawls, _now=self.now)
    self.assertEquals(0, crawls_purged)
    self.assertEquals(None, error)

  def testPurgeCrawls_DeadlineExceeded(self):
    crawls_before, crawls_after = self._MakeSomeCrawls()

    self.mox.StubOutWithMock(cap_mirror, 'PurgeCrawl')
    cap_mirror.logging.info(mox.StrContains('Purging crawls'), self.cutoff_date)

    # Since we don't actually purge the crawls with the mock, we will
    # repeatedly attempt the same crawl.
    expected_crawls_purged = 5
    for x in xrange(expected_crawls_purged):
      cap_mirror.PurgeCrawl(crawls_before[0].key(), self.batch_size)

    # Let the final attempt fail.
    cap_mirror.PurgeCrawl(mox.IgnoreArg(), self.batch_size).AndRaise(
        DeadlineExceededError())

    self.mox.ReplayAll()

    last_crawls = frozenset()
    actual_crawls_purged, error = cap_mirror.PurgeCrawls(
        self.days_to_keep, self.batch_size, last_crawls, _now=self.now)
    self.assertEqual(expected_crawls_purged, actual_crawls_purged)
    self.assertEqual('Deadline exceeded', error)

  def testPurgeCrawls_exception(self):
    crawls_before, crawls_after = self._MakeSomeCrawls()

    self.mox.StubOutWithMock(cap_mirror, 'PurgeCrawl')
    cap_mirror.logging.info(mox.StrContains('Purging crawls'), self.cutoff_date)

    # Since we don't actually purge the crawls with the mock, we will
    # repeatedly attempt the same crawl.
    expected_crawls_purged = 5
    for x in xrange(expected_crawls_purged):
      cap_mirror.PurgeCrawl(crawls_before[0].key(), self.batch_size)

    # Let the final attempt fail.
    cap_mirror.PurgeCrawl(mox.IgnoreArg(), self.batch_size).AndRaise(
        ValueError('foobar'))
    cap_mirror.logging.exception(mox_util.AsStrContains('foobar'))

    self.mox.ReplayAll()

    last_crawls = frozenset()
    actual_crawls_purged, error = cap_mirror.PurgeCrawls(
        self.days_to_keep, self.batch_size, last_crawls, _now=self.now)
    self.assertEqual(expected_crawls_purged, actual_crawls_purged)
    self.assertIn('foobar', error)

  def testPurgeCrawls_heedsCutoffDate(self):
    crawls_before, crawls_after = self._MakeSomeCrawls()

    self.mox.StubOutWithMock(cap_mirror, 'PurgeCrawl')
    cap_mirror.PurgeCrawl = self._PurgeCrawl
    cap_mirror.logging.info(mox.StrContains('Purging crawls'), self.cutoff_date)
    cap_mirror.logging.info(mox.StrContains('No more crawls'))
    self.mox.ReplayAll()

    last_crawls = frozenset()
    actual_crawls_purged, error = cap_mirror.PurgeCrawls(
        self.days_to_keep, self.batch_size, last_crawls, _now=self.now)

    self.assertEquals(actual_crawls_purged, len(crawls_before))
    self.assertEquals(None, error)
    self.assertSameElements([crawl.key() for crawl in crawls_after],
                            [crawl.key() for crawl in cap_schema.Crawl.all()])

  def testPurgeCrawls_heedsLastCrawls(self):
    crawls_before, crawls_after = self._MakeSomeCrawls()
    last_crawl = crawls_before[1]
    last_crawls = frozenset([last_crawl.key()])

    self.mox.StubOutWithMock(cap_mirror, 'PurgeCrawl')
    cap_mirror.PurgeCrawl = self._PurgeCrawl
    cap_mirror.logging.info(mox.StrContains('Purging crawls'), self.cutoff_date)
    cap_mirror.logging.info(mox.StrContains('Cannot purge crawl'),
                            last_crawl.key())
    self.mox.ReplayAll()

    actual_crawls_purged, error = cap_mirror.PurgeCrawls(
        self.days_to_keep, self.batch_size, last_crawls, _now=self.now)

    # Only the crawl that preceeded the last_crawl will be purged.
    self.assertEquals(actual_crawls_purged, 1)
    self.assertEquals(None, error)
    self.assertSameElements(
        [crawl.key() for crawl in crawls_after + crawls_before[1:]],
        [crawl.key() for crawl in cap_schema.Crawl.all()])


class PurgeCrawlTest(CapMirrorTestBase):
  """Tests for cap_mirror.PurgeCrawl."""

  def testPurgeCrawl_nominal(self):
    num_crawls = 3
    crawls = cap_test_util.NewCrawls(num_crawls, fake_clock.FakeNow())
    # Obsolete models should also be purged.
    obsolete_models = [cap_schema.CapResource, cap_schema.CapArea,
                       cap_schema.CapInfo, cap_schema.Cap]
    models = [cap_schema.CapAlert, cap_schema.CrawlShard] + obsolete_models
    for crawl in crawls:
      for model in models:
        model_instance = model(crawl=crawl)
        model_instance.put()

    # Pick one crawl to purge.
    crawl = crawls[1]
    crawl_key = crawl.key()
    cap_mirror.logging.info(mox.StrContains('Purging crawl'), crawl_key)
    for model in models:
      cap_mirror.logging.info(
          mox.StrContains('Purging %s for crawl'),
          model.__name__, crawl_key).InAnyOrder()
    cap_mirror.logging.info(mox.StrContains('Deleting crawl'), crawl_key)
    self.mox.ReplayAll()

    batch_size = 10
    cap_mirror.PurgeCrawl(crawl_key, batch_size)
    for model in models:
      self.assertListEqual([], list(model.gql('WHERE crawl = :1', crawl_key)))
    self.assertListEqual(
        [], list(cap_schema.Crawl.gql('WHERE __key__ = :1', crawl_key)))


# TODO(Matt Frantz): Write tests for the webapp.RequestHandler subclasses.


def main(unused_argv):
  googletest.main()


if __name__ == '__main__':
  app.run()
