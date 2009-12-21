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

"""Integration test for cap_crawl."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import cgi
import datetime
import os.path
import re
import time
import urlparse

import google3
import mox
import pytz

from google3.pyglib import app
from google3.pyglib import logging
from google3.pyglib import resources
from google3.testing.pybase import googletest

from google3.dotorg.gongo.appengine_cap2kml import cap_crawl
from google3.dotorg.gongo.appengine_cap2kml import cap_schema
from google3.dotorg.gongo.appengine_cap2kml import db_test_util
from google3.dotorg.gongo.appengine_cap2kml import fake_clock
from google3.dotorg.gongo.appengine_cap2kml import taskqueue_test_util
from google3.dotorg.gongo.appengine_cap2kml import web_query


class CapCrawlTestBase(mox.MoxTestBase, db_test_util.DbTestBase,
                       taskqueue_test_util.TaskQueueTestBase):
  """Base class for all cap_crawl integration tests."""

  CRAWL_PERIOD_IN_MINUTES = 60
  CRAWL_PERIOD = datetime.timedelta(minutes=CRAWL_PERIOD_IN_MINUTES)

  # taskqueue_test_util.TaskQueueTestBase allows this to specify the location
  # of queue.yaml.
  @property
  def QUEUE_YAML_ROOT_PATH(self):
    queue_yaml = resources.GetResourceFilenameInDirectoryTree(
        os.path.join('google3', 'dotorg', 'gongo', 'appengine_cap2kml',
                     'queue.yaml'))
    return os.path.dirname(queue_yaml)

  def setUp(self):
    super(CapCrawlTestBase, self).setUp()
    self.now = fake_clock.FakeNow()
    # Stub out anything that we never want to call for real.
    self.mox.StubOutWithMock(cap_crawl, 'urlfetch')
    self.mox.StubOutWithMock(time, 'sleep')

  def _AddFeed(self, feed_url):
    """Adds a single Feed object to the Datastore.

    Args:
      feed_url: URL of the feed index (str)

    Returns:
      cap_schema.Feed object
    """
    feed = cap_schema.Feed(key_name=feed_url, url=feed_url, is_root=True,
                           cap_period_in_minutes=self.CRAWL_PERIOD_IN_MINUTES)
    feed.put()
    return feed

  def _Crawl(self):
    """Performs a crawl."""
    crawl_controller = cap_crawl.CrawlNudge(_now=self.now)
    if not crawl_controller.GetCrawl():
      # Nothing to crawl, so no tasks should be generated.
      self.assertListEqual(
          [], self.task_stub.GetTasks(cap_crawl.WORKER_TASKQUEUE_NAME))
      self.assertListEqual(
          [], self.task_stub.GetTasks(cap_crawl.PUSH_TASKQUEUE_NAME))
      return

    # Loop until there are no more tasks.
    tasks = ['dummy']
    while tasks:
      # Empty the push task queue.
      tasks = self.task_stub.GetTasks(cap_crawl.PUSH_TASKQUEUE_NAME)
      self.task_stub.FlushQueue(cap_crawl.PUSH_TASKQUEUE_NAME)
      for task in tasks:
        (_, _, path, _, query, _) = urlparse.urlparse(task['url'])
        self.assertEquals('/crawlpush', path)
        params = cgi.parse_qs(query)
        self.assertIn('crawl', params)
        self.assertIn('feed', params)
        self.assertIn('url', params)
        crawl_keys = params['crawl']
        self.assertEquals(1, len(crawl_keys))
        feed_keys = params['feed']
        self.assertEquals(1, len(feed_keys))
        urls = params['url']
        self.assertEquals(1, len(urls))
        cap_crawl.CrawlPush(crawl_keys[0], feed_keys[0], urls[0])

      # Empty the worker task queue.
      tasks = self.task_stub.GetTasks(cap_crawl.WORKER_TASKQUEUE_NAME)
      self.task_stub.FlushQueue(cap_crawl.WORKER_TASKQUEUE_NAME)
      for task in tasks:
        (_, _, path, _, query, _) = urlparse.urlparse(task['url'])
        self.assertEquals('/crawlworker', path)
        params = cgi.parse_qs(query)
        self.assertIn('shard', params)
        shard_keys = params['shard']
        self.assertEquals(1, len(shard_keys))
        worker_controller = cap_crawl.CrawlWorker(shard_keys[0], _now=self.now)
        self.assertTrue(worker_controller.GetShard().is_done)

    # Nudge it again, which should finish it.
    logging.debug('Finishing test crawl')
    crawl_controller = cap_crawl.CrawlNudge(_now=self.now)
    crawl = crawl_controller.GetCrawl()
    self.assertTrue(crawl)
    self.assertTrue(crawl.is_done)


def _GetModels(model_class, sort_key, **kwargs):
  """Queries the Datastore for a models having specified attributes.

  Args:
    model_class: Class object of a db.Model subclass
    sort_key: Function that returns the sort key for the model instances.
    kwargs: Attribute names and values to restrict the query.

  Returns:
    Sorted list of model instances.
  """
  model_name = model_class.__name__
  if kwargs:
    predicates = []
    for attribute, argument in kwargs.iteritems():
      predicate = web_query.SimpleComparisonPredicate(
          model_name, attribute, argument, web_query.Operators.SCALAR_EQUALS)
      predicates.append(predicate)

    query = web_query.Query(predicates)
    gql_list, gql_params = query.ApplyToGql(model_name)
    db_query = model_class.gql('WHERE %s' % ' AND '.join(gql_list),
                               **gql_params)
  else:
    db_query = model_class.all()

  return sorted(db_query, key=sort_key)


def _GetCrawls(**kwargs):
  """Queries Crawl instances.

  Args:
    kwargs: Attribute names and values to restrict the query.

  Returns:
    List of cap_schema.Crawl instances sorted by 'started' timestamp.
  """
  return _GetModels(cap_schema.Crawl, lambda crawl: crawl.started, **kwargs)


def _GetShards(**kwargs):
  """Queries CrawlShard instances.

  Args:
    kwargs: Attribute names and values to restrict the query.

  Returns:
    List of cap_schema.CrawlShard instances sorted by 'started' timestamp.
  """
  return _GetModels(cap_schema.CrawlShard, lambda shard: shard.started,
                    **kwargs)


def _GetFeeds(**kwargs):
  """Queries Feed instances.

  Args:
    kwargs: Attribute names and values to restrict the query.

  Returns:
    List of cap_schema.Feed instances sorted by 'url'.
  """
  return _GetModels(cap_schema.Feed, lambda feed: feed.url, **kwargs)


def _GetAlerts(**kwargs):
  """Queries CapAlert instances.

  Args:
    kwargs: Attribute names and values to restrict the query.

  Returns:
    List of cap_schema.CapAlert instances sorted by 'url'.
  """
  return _GetModels(cap_schema.CapAlert, lambda alert: alert.url, **kwargs)


class InternalTest(CapCrawlTestBase):
  """Integration test using internal test data."""

  def testFakeFeedIndex1(self):
    self.mox.ReplayAll()

    feed_url = '_FAKE_FEED_URL_1_'
    self._AddFeed(feed_url)
    self._Crawl()

    # Should be one crawl.
    crawls = _GetCrawls()
    self.assertEquals(len(crawls), 1)
    crawl = crawls[0]
    self.assertEquals(crawl.is_done, True)
    self.assertListEqual([feed_url], crawl.feed_urls)

    # Should be one shard per cap, plus one for the feed itself.
    shards = _GetShards()
    self.assertTrue(len(shards) >= 1)

    # First one should be the feed.
    cap_shards = list(shards)
    feed_shard = cap_shards.pop(0)
    self.assertEquals(feed_shard.url, feed_url)
    self.assertEquals(feed_shard.error, None,
                      "Unexpected error:\n%s" % feed_shard.error)

    # We should have three more, one per fake cap.
    self.assertSameElements(['testdata/fake1_cap1.xml',
                             'testdata/fake1_cap2.xml',
                             'testdata/fake1_cap3.xml'],
                            [shard.url for shard in cap_shards])

    # We should have three alerts.
    alerts = _GetAlerts()
    for alert in alerts:
      self.assertTrue(
          re.search('Error copying .*identifier', repr(alert.parse_errors)),
          'Expected error not found in %r' % alert.parse_errors)

    # Clock should advance, and the crawl should finish after all shards.
    self.assertEquals(crawl.started, fake_clock.FakeNow.DEFAULT_NOW)
    self.assertTrue(crawl.finished > crawl.started)
    self.assertTrue(crawl.started < min([shard.started for shard in shards]))
    self.assertTrue(crawl.finished > max([shard.finished for shard in shards]))

    # Feed should be marked as having been crawled.
    feeds = _GetFeeds()
    self.assertListEqual([feed_url], [feed.url for feed in feeds])
    feed = feeds[0]
    self.assertEquals(feed.last_crawl.started, crawl.started)

    # As long as we haven't reached the crawl period, we shouldn't have
    # another crawl.
    self.assertTrue(self.now.now < crawl.started + self.CRAWL_PERIOD)
    self._Crawl()
    crawls = _GetCrawls()
    self.assertEquals(len(crawls), 1)

    # Once we go past the crawl period, we should be able to crawl again.
    self.now.now += self.CRAWL_PERIOD
    self._Crawl()
    crawls = _GetCrawls()
    self.assertEquals(len(crawls), 2)

    # Twice as many shards.
    shards_after_second_crawl = _GetShards()
    self.assertEquals(len(shards_after_second_crawl), len(shards) * 2)

  def testAquilaFeed(self):
    self.mox.ReplayAll()

    feed_url = 'testdata/aquila_feed1.xml'
    self._AddFeed(feed_url)
    self._Crawl()

    # Should be one shard per cap, plus one for the feed itself.
    shards = _GetShards()

    cap_urls = ['testdata/aquila_cap5.xml',
                'testdata/aquila_cap2.xml',
                'testdata/aquila_cap3.xml']

    self.assertSameElements([feed_url] + cap_urls,
                            [shard.url for shard in shards])

    # Should be no errors.
    self.assertListEqual([None] * len(shards),
                         [shard.error for shard in shards])

    # Should have three alerts.
    alerts = _GetAlerts()
    self.assertSameElements(cap_urls, [alert.url for alert in alerts])

    # After advancing to the next crawl period, we should be able to crawl
    # again.
    self.now.now += self.CRAWL_PERIOD
    self._Crawl()
    alerts_after_second_crawl = _GetAlerts()
    self.assertEquals(len(alerts_after_second_crawl), len(alerts) * 2)

    # There should be two CapAlerts for the same URL.
    cap2_alerts = [x for x in alerts_after_second_crawl
                   if x.url == 'testdata/aquila_cap2.xml']
    self.assertEquals(len(cap2_alerts), 2)

    # The two CapAlerts should be from different crawls.
    self.assertTrue(cap2_alerts[0].crawl.started !=
                    cap2_alerts[1].crawl.started)

  def testWeatherFeed(self):
    self.mox.ReplayAll()

    feed_url = 'testdata/weather_feed.xml'
    self._AddFeed(feed_url)
    self._Crawl()

    # Check that we have no parse errors.
    alerts = _GetAlerts()
    parse_errors = []
    for alert in alerts:
      parse_errors.extend(alert.parse_errors)
    self.assertSameElements([], parse_errors)

  # TODO(Matt Frantz): Add test for _FAKE_FEED_URL_2_.


def main(unused_argv):
  googletest.main()


if __name__ == '__main__':
  app.run()
