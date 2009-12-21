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

"""Crawl/index CAP feeds.

Contains the crawl/index code, accessed at the /crawl URL.  Visits selected
websites and fetches CAP data, which it stores in Datastore.  Data can be
subsequently queried with the cap_query module.

There are two main concrete classes, CrawlControllerWorker and
CrawlControllerMaster, that implement the distinct behavior of the worker and
master threads, respectively.

The master thread (at /crawl) is responsible for reading the list of feeds
(from the cap_schema.Feed Datastore) and seeding the task queues.  The task
queues persist in cap_schema.CrawlShard models in the Datastore.  Each
CrawlShard instance is a single atom of work, which is a single URL to visit.
The URL may be CAP or an index (RSS or ATOM) of CAP's.

The worker thread (at /crawlworker) is provided with a single shard of work
consisting of a single URL to fetch.  If an index of CAP URL's is retrieved,
it may push shards onto the task queue.

A thread is implemented not using Python threads (which are disallowed in
AppEngine), but by servicing a unique request under the /crawl URL.  Those
requests are initiated by cron (see cron.yaml) and by the Task Queue API (see
queue.yaml).
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import datetime
import logging
import os
import random
import sys
import traceback

try:
  # google3
  import google3
  import cap as caplib

  from google3.apphosting.api import urlfetch
  from google3.apphosting.api import taskqueue
  from google3.apphosting.ext import db
  from google3.apphosting.ext import webapp
  from google3.apphosting.ext.webapp.util import run_wsgi_app
  from google3.apphosting.runtime.apiproxy_errors import DeadlineExceededError
  from google3.pyglib import logging

  from google3.dotorg.gongo.appengine_cap2kml import cap_fake
  from google3.dotorg.gongo.appengine_cap2kml import cap_index_parse
  from google3.dotorg.gongo.appengine_cap2kml import cap_parse_db
  from google3.dotorg.gongo.appengine_cap2kml import cap_parse_mem
  from google3.dotorg.gongo.appengine_cap2kml import cap_schema
  from google3.dotorg.gongo.appengine_cap2kml import db_util
  from google3.dotorg.gongo.appengine_cap2kml import webapp_util
  from google3.dotorg.gongo.appengine_cap2kml import xml_util

except ImportError:
  import cap as caplib

  from google.appengine.api import urlfetch
  from google.appengine.api.labs import taskqueue
  from google.appengine.ext import db
  from google.appengine.ext import webapp
  from google.appengine.ext.webapp.util import run_wsgi_app
  from google.appengine.runtime import DeadlineExceededError

  import cap_fake
  import cap_index_parse
  import cap_parse_db
  import cap_parse_mem
  import cap_schema
  import db_util
  import webapp_util
  import xml_util


class Error(Exception):
  pass


class UrlAlreadyCrawledError(Error):
  pass


# Format string for an ATOM index of links.
_ATOM_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<atom:feed xmlns:atom = "http://www.w3.org/2005/Atom">
  %(entries)s
</atom:feed>
"""

# Format string for a single ATOM entry with a link.
_ATOM_ENTRY = """<atom:entry><atom:link href="%(link)s" /></atom:entry>"""


def _MakeAtomFeed(urls):
  """Returns ATOM that points to a list of URL's.

  Args:
    urls: List of URL's (list of str)

  Returns:
    ATOM XML (str)
  """
  entries = '\n  '.join([_ATOM_ENTRY % dict(link=x) for x in urls])
  return _ATOM_INDEX % locals()


# Max out the deadline for fetching URL's, according to the doc:
# http://code.google.com/appengine/docs/python/urlfetch/fetchfunction.html
URLFETCH_DEADLINE_SECS = 10


def FetchUrl(url):
  """Returns the contents of the URL, allowing for 'testdata/' local files.

  Also supports fake feed URL's defined in cap_fake.FAKE_FEED_URLS.

  Args:
    url: URL, possibly beginning with 'testdata/' (string)

  Returns:
    Contents of the URL (string)
  """
  if url in cap_fake.FAKE_FEED_URLS:
    return _MakeAtomFeed(cap_fake.FAKE_FEED_URLS[url]())
  elif url.startswith('testdata/'):
    path = os.path.join(os.path.dirname(__file__), url)
    try:
      fd = open(path, mode='r')
      try:
        data = fd.read()
        return data
      finally:
        fd.close()
    except DeadlineExceededError:
      raise
    except:
      logging.error('Cannot read file: %s', path)
      raise
  else:
    return urlfetch.fetch(url, deadline=URLFETCH_DEADLINE_SECS).content


def GetCap(feed, crawl, cap_url):
  """Retrieves a CAP file and saves it in the Datastore.

  Args:
    feed: Feed object or reference
    crawl: cap_schema.Crawl object
    cap_url: URL of a CAP file (string)

  Returns:
    cap_schema.CapAlert object (already populated and saved)
  """
  cap_text = xml_util.ParseText(FetchUrl(cap_url))
  parser = cap_parse_mem.MemoryCapParser()
  new_alert_model = lambda: caplib.Alert()
  alert_mem, errors = parser.MakeAlert(new_alert_model, cap_text)
  alert_db = cap_parse_db.MakeDbAlertFromMem(alert_mem)
  alert_db.crawl = crawl
  alert_db.feed = feed
  alert_db.url = cap_url
  alert_db.text = cap_text
  for error in errors:
    alert_db.parse_errors.append(xml_util.ParseText(str(error)))
  # Save the alert model to the db.
  alert_db.put()
  return alert_db


def GetFeedIndex(feed_url):
  """Returns the list of CAP URL's in the current feed's index.

  Args:
    feed_url: URL of the feed (str)

  Returns:
    List of CAP URL's (strings)

  Raises:
    CapIndexFormatError: if there is a problem parsing.
    Exception: if problems fetching the URL.
  """
  index_text = FetchUrl(feed_url)
  return cap_index_parse.ParseCapIndex(index_text)


def _CrawlShardKeyName(crawl, url):
  """Generates a stable, unique key name for a URL in a particular crawl.

  Args:
    crawl: cap_schema.Crawl object
    url: URL that will be crawled (str)

  Returns:
    Key name (str) for the cap_schema.CrawlShard model.
  """
  return 'CrawlShard %s %s' % (crawl.started, url)


# Name of the task queue for /crawlpush, which corresponds to the
# configuration in queue.yaml.
PUSH_TASKQUEUE_NAME = 'crawlpush'


def _EnqueuePush(crawl, feed, url):
  """Adds a shard to the crawl task queue.

  Args:
    crawl: cap_schema.Crawl object
    feed: cap_schema.Feed object
    url: URL to be fetched (str)
  """
  queue = taskqueue.Queue(name=PUSH_TASKQUEUE_NAME)
  task = taskqueue.Task(
      url='/crawlpush', method='GET',
      params={'crawl': str(crawl.key()), 'feed': str(feed.key()), 'url': url})
  queue.add(task)


def _MaybePushShardUnsafe(crawl, feed, url):
  """Pushes a shard of work onto an appropriate queue.

  Called by _MaybePushShard to wrap in a transaction.

  Args:
    crawl: cap_schema.Crawl object
    feed: cap_schema.Feed object
    url: URL to be fetched (str)

  Returns:
    (shard, is_new)
    shard: cap_schema.CrawlShard object, possibly new.
    is_new: If True, shard was just added.

  Postconditions:
    May add a new CrawlShard.
  """
  logging.debug('MaybePushShard %r', url)
  assert crawl
  # Use a key that will help us know whether this URL has been crawled on
  # this crawl before.
  key_name = _CrawlShardKeyName(crawl, url)

  # See if we already exist.
  shard = cap_schema.CrawlShard.get_by_key_name(key_name)
  is_new = not shard
  if is_new:
    shard = cap_schema.CrawlShard(
        key_name=key_name, crawl=crawl, feed=feed, url=url)
    shard.put()

  return (shard, is_new)


def _MaybePushShard(crawl, feed, url):
  """Pushes a shard of work onto an appropriate queue.

  Args:
    crawl: cap_schema.Crawl object
    feed: cap_schema.Feed object
    url: URL to be fetched (str)

  Returns:
    (shard, is_new)
    shard: cap_schema.CrawlShard object, possibly new.
    is_new: If True, shard was just added.

  Postconditions:
    May add a new CrawlShard.
  """
  shard, is_new = db.run_in_transaction(_MaybePushShardUnsafe, crawl, feed, url)

  # Add the shard to the task queue.  Avoid enqueueing completed shards.
  if is_new:
    _EnqueueShard(str(shard.key()))

  return shard, is_new


# Name of the task queue for /crawlworker, which corresponds to the
# configuration in queue.yaml.
WORKER_TASKQUEUE_NAME = 'crawlworker'


def _EnqueueShard(shard_key):
  """Adds a shard to the crawl task queue.

  Args:
    shard_key: Encoded key for the cap_schema.CrawlShard model (str).
  """
  queue = taskqueue.Queue(name=WORKER_TASKQUEUE_NAME)
  task = taskqueue.Task(url='/crawlworker', method='GET',
                        params={'shard': shard_key})
  queue.add(task)


class CrawlControllerWorker(object):
  """Controls a single crawl worker.

  The worker performs one shard of work, recording the results in the
  cap_schema.CrawlShard model.  It may create and enqueue other shards of
  work.
  """

  def __init__(self, shard_key, _now=datetime.datetime.now):
    """Initializes a CrawlControllerWorker object.

    Args:
      shard_key: Encoded key of the cap_schema.CrawlShard (str or unicode)
      _now: dependency injection of clock function that returns
          datetime.datetime object.
    """
    self._now = _now
    self._shard = cap_schema.CrawlShard.get(db.Key(shard_key))
    if not self._shard:
      logging.error('No shard having key %r', shard_key)

  def GetShard(self):
    """Returns the model of the current crawl shard.

    Returns:
      cap_schema.CrawlShard object.
    """
    return self._shard

  def DoShard(self):
    """Processes a single unit of work (a URL).

    Postconditions:
      Updates shard.started and shard.completed.
      May update the CapAlert Datastore.
      May add more CrawlShards (if nested index)
      Updates shard.error, if an error occurs.
      May push a new feed into the queue, affecting _NextFeed.
    """
    shard = self._shard
    if not shard:
      return

    # Avoid fetching the same shard twice.  This shouldn't happen because of
    # the way _MaybePushShard works.
    if shard.is_done:
      logging.error('Shard is already done: %r', shard.url)
      return

    shard.started = self._now()
    url = shard.url
    # Catch any errors for this URL, so that we can record them in the shard
    # record.
    try:
      # Assume the URL contains CAP, but catch NotCapError if it is not.
      try:
        cap = GetCap(shard.feed, shard.crawl, url)
        shard.parse_errors = cap.parse_errors
        logging.debug('Created CAP for %r', url)
      except cap_parse_mem.NotCapError:
        logging.debug('Not CAP ... assuming CAP index: %r', url)
        # Try to process the URL as an index.
        urls = GetFeedIndex(url)
        logging.debug('Found %d URLs in nested index', len(urls))
        for url in urls:
          _EnqueuePush(shard.crawl, shard.feed, url)
    except (DeadlineExceededError, AssertionError):
      raise
    except Exception, e:
      logging.error('Skipping URL %r: %r', url, e)
      shard.error = db.Text('Skipping URL %r: %r: %s' %
                            (url, e, traceback.format_exc()))

    # Whether or not we were successful, we are done with this shard.
    shard.is_done = True
    shard.finished = self._now()
    shard.put()


class CrawlControllerMaster(object):
  """Controls the crawl master.

  The master is responsible for starting a new crawl and for marking crawls as
  done.
  """

  def __init__(self, _crawl=None, _now=datetime.datetime.now):
    """Initializes a CrawlControllerWorker object.

    Args:
      _crawl: dependency injection of the crawl object (cap_schema.Crawl)
      _now: dependency injection of clock function that returns
          datetime.datetime object.
    """
    self._now = _now
    if _crawl:
      self._crawl = _crawl
    else:
      self._EnsureCrawl()

  def GetCrawl(self):
    """Returns the model of the current crawl.

    Returns:
      cap_schema.Crawl object, or None if there is no crawl in progress.
    """
    return self._crawl

  def _EnsureCrawl(self):
    """Retrieves the crawl in progress.

    As master, we create a new one if necessary.  If there is an existing
    crawl that is done, we mark it so.

    Postconditions:
      self._crawl is assigned cap_schema.Crawl object, or None if there is
      nothing to crawl.
    """
    self._crawl = self._CrawlInProgress()
    if self._crawl:
      # There is a crawl in progress, so check if there are any more shards.
      if self._AreMoreShardsInProgress():
        logging.debug('Waiting for other workers')
        return
      else:
        # Mark this crawl done before starting a new one.
        self._CrawlIsDone()
    else:
      # We're the master, so start a new crawl.
      self._NewCrawl()

  def _AreMoreShardsInProgress(self):
    """Determines if any worker has pending work.

    Returns:
      True, iff there are incomplete shards for the current crawl.
    """
    return bool(self._QueryAnyIncompleteShard())

  def _QueryAnyIncompleteShard(self):
    """Finds an incomplete shard for any worker in the current crawl.

    Returns:
      db.Key object for cap_schema.CrawlShard object, or None if there are no
      incomplete shards.
    """
    crawl = self._crawl
    assert crawl
    shard = db.GqlQuery(
        'SELECT __key__ FROM CrawlShard WHERE crawl = :1 AND is_done = :2',
        crawl, False).get()
    return shard

  def _CrawlInProgress(self):
    """Returns the most recent Crawl that is still in progress.

    Returns:
      cap_schema.Crawl object, or None if all existing crawls are complete.
    """
    query = cap_schema.Crawl.gql(
        'WHERE is_done = :1 ORDER BY started DESC', False)
    crawl = query.get()
    if crawl:
      # We have an unfinished crawl, so use it.
      logging.debug('Found crawl in progress (started %s)', crawl.started)
      return crawl
    else:
      return None

  def _CrawlIsDone(self):
    """Called when we detect that the current crawl is complete.

    Postconditions:
      Current Crawl.is_done is set to True.
      Current Crawl.finished is set to now.
      Current Crawl is saved.
      All relevant Feed.last_crawl references are set to the current crawl.
    """
    logging.debug('Crawl is done')
    # Update the Datastore.
    crawl = self._crawl
    assert crawl
    crawl.is_done = True
    crawl.finished = self._now()
    crawl.put()
    # Update the feeds with the last completed crawl.
    for feed in cap_schema.Feed.gql('WHERE url IN :1', crawl.feed_urls):
      feed.last_crawl = crawl
      feed.put()

  def _NewCrawl(self):
    """Starts a new crawl.

    Postconditions:
      self._crawl is assigned cap_schema.Crawl object, or None if there is
      nothing to crawl.
    """
    # Figure out what feeds we'll be crawling (if any).
    crawl_started = self._now()
    feeds = self._GetFeeds(crawl_started)
    if not feeds:
      logging.debug('No feeds to crawl')
      self._crawl = None
      return

    # Start a new crawl.
    crawl = cap_schema.Crawl()
    self._crawl = crawl
    crawl.started = crawl_started
    crawl.feed_urls = [feed.url for feed in feeds]
    crawl.put()
    logging.debug('Started new crawl at %s', crawl.started)

    # Create one shard per Feed.
    for feed in feeds:
      _EnqueuePush(crawl, feed, feed.url)

  def _GetFeeds(self, crawl_started):
    """Returns a list of all feeds to be crawled.

    The crawl period for each feed is considered, relative to the specified
    start time of the current crawl.

    Args:
      crawl_started: Timestamp when the current crawl started (datetime)

    Returns:
      List of cap_schema.Feed objects
    """
    query = cap_schema.Feed.gql(
        'WHERE is_crawlable = :1 AND is_root = :2', True, True)
    feeds = []
    for feed in query:
      last_crawl = db_util.SafelyDereference(feed, 'last_crawl')
      if last_crawl:
        last_crawled = last_crawl.started
      else:
        last_crawled = None

      # If we've never crawled this feed, or we haven't crawled it recently,
      # add it to the list.
      if not last_crawled or crawl_started > last_crawled + datetime.timedelta(
          minutes=feed.crawl_period_in_minutes):
        feeds.append(feed)
    return feeds


def CrawlNudge(_now=datetime.datetime.now):
  """Seeds the task queues for a crawl.

  Args:
    _now: dependency injection of clock function that returns
        datetime.datetime object.

  Returns:
    CrawlControllerMaster object
  """
  controller = CrawlControllerMaster(_now=_now)
  return controller


class CrawlNudgeHandler(webapp.RequestHandler):
  """Responds to requests from cron to initiate a new crawl."""

  def get(self):
    controller = CrawlNudge()

    # We're done!  If we have a crawl record, wrap it in a ShadowCrawl to
    # provide the Django template access to extended functionality.
    crawl = controller.GetCrawl()
    if crawl:
      crawl = cap_schema.ShadowCrawl(crawl)

    webapp_util.WriteTemplate(self.response, 'crawl.html', dict(crawl=crawl))


def CrawlPush(crawl_key, feed_key, url):
  """Decodes the keys and maybe pushes a shard of work.

  Args:
    crawl_key: Key (unicode or str) of a cap_schema.Crawl
    feed_key: Key (unicode or str) of a cap_schema.Feed
    url: URL that needs to be crawled (unicode or str)

  Returns:
    (shard, is_new)
    shard: cap_schema.CrawlShard object, possibly new.
    is_new: If True, shard was just added.
  """
  crawl = cap_schema.Crawl.get(db.Key(crawl_key))
  if not crawl:
    logging.error('No crawl having key %r', crawl_key)
    return

  feed = cap_schema.Feed.get(db.Key(feed_key))
  if not feed:
    logging.error('No feed having key %r', feed_key)
    return

  return _MaybePushShard(crawl, feed, url)


class CrawlPushHandler(webapp.RequestHandler):
  """Responds to requests to push a URL into the crawl queue."""

  def get(self):
    crawl_key = self.request.get('crawl')
    feed_key = self.request.get('feed')
    url = self.request.get('url')
    if crawl_key and feed_key and url:
      CrawlPush(crawl_key, feed_key, url)
    else:
      logging.error('Must specify crawl, feed, and url')


def CrawlWorker(shard_key, _now=datetime.datetime.now):
  """Seeds the task queues for a crawl.

  Args:
    shard_key: Key of a cap_schema.CrawlShard
    _now: dependency injection of clock function that returns
        datetime.datetime object.

  Returns:
    CrawlControllerWorker object
  """
  controller = CrawlControllerWorker(shard_key, _now=_now)
  controller.DoShard()
  return controller


class CrawlWorkerHandler(webapp.RequestHandler):
  """Responds to requests from the task queue to crawl a URL."""

  def get(self):
    shard_key = self.request.get('shard')
    if shard_key:
      controller = CrawlWorker(shard_key)
    else:
      logging.error('Must specify shard')


application = webapp.WSGIApplication(
    [('/crawl', CrawlNudgeHandler),
     ('/crawlpush', CrawlPushHandler),
     ('/crawlworker', CrawlWorkerHandler),
     ],
    debug=True)


def main():
  run_wsgi_app(application)


if __name__ == '__main__':
  main()
