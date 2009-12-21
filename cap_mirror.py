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

"""Administrative interface to the CAP mirror.

Contains control and display interfaces designed for an administrator or
developer, including the following interfaces:

/feeds: Display of cap_schema.Feed entries in the Datastore, with the ability
to edit parameters that control how each feed is crawled.

/savefeed: Handles editing from the /feeds page.

/resetfeeds: Replaces the cap_schema.Feed Datastore with new instances based
on hardcoded lists (FEED_LISTS).

/clearcaps: Deletes all cap_schema.CapAlert data.

/clearcrawls: Deletes all cap_schema.Crawl and cap_schema.CrawlShard data.

/purgecrawls: Deletes the oldest data up to, but not including, the data from
the most recent crawl.

/crawls: Displays a tabular view of crawl (cap_schema.Crawl) history.

/shards: Displays a tabular view of shards (cap_schema.CrawlShard) from a
single crawl.

/caps: Displays a tabular view of CAP data (cap_schema.CapAlerta) from a
single crawl.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import cgi
import datetime
import logging

try:
  from google3.apphosting.ext import db
  from google3.apphosting.ext import webapp
  from google3.apphosting.ext.webapp.util import run_wsgi_app
  from google3.apphosting.runtime.apiproxy_errors import DeadlineExceededError
  from google3.pyglib import logging

  from google3.dotorg.gongo.appengine_cap2kml import cap_fake
  from google3.dotorg.gongo.appengine_cap2kml import cap_schema
  from google3.dotorg.gongo.appengine_cap2kml import paged_query
  from google3.dotorg.gongo.appengine_cap2kml import webapp_util

except ImportError:
  from google.appengine.ext import db
  from google.appengine.ext import webapp
  from google.appengine.ext.webapp.util import run_wsgi_app
  from google.appengine.runtime import DeadlineExceededError

  import cap_fake
  import cap_schema
  import paged_query
  import webapp_util


class Error(Exception):
  pass


class SaveFeedError(Error):
  """Raised if anything goes wrong with SaveFeed."""


class ShardsError(Error):
  """Raised if anything goes wrong with the /shards screen."""


# Selection of hardcoded feed lists.
FEED_LISTS = {
    'internal': [
        'testdata/rss_feed1.xml',
        'testdata/atom_feed1.xml',
        'testdata/aquila_feed1.xml',
        'testdata/parent_feed.xml',
        'testdata/weather_feed.xml',
        ] + list(cap_fake.FAKE_FEED_URLS.keys()),
    'external': [
        # California weather
        'http://www.weather.gov/alerts-beta/ca.php?x=0',
        # U.S. weather
        'http://www.weather.gov/alerts-beta/us.php?x=0',
        # Earthquakes
        ('http://earthquake.usgs.gov/eqcenter/recenteqsww/catalogs/' +
         'caprss7days5.xml'),
        # U.S. landslides
        'http://www.usgs.gov/hazard_alert/alerts/landslides.rss',
        # U.S. volcanos
        'http://volcano.wr.usgs.gov/rss/vhpcaprss.xml',
        # Anguilla
        'http://ddmcap.hopto.org/index.atom',
        # Emergency Digital Information Service (EDIS) - California
        'http://edis.oes.ca.gov/index.atom',
        # Contra Costa County, California, Sherriff's Office, Emergency Services
        'http://cwscap.cccounty.us/index.atom',
        ],
    }


def DefaultFeeds(feed_list):
  """Returns the default list of feeds.

  Args:
    feed_list:

  Returns:
    List of Feed objects
  """
  assert feed_list in FEED_LISTS
  feed_urls = FEED_LISTS[feed_list]
  feeds = []
  for url in feed_urls:
    feeds.append(cap_schema.Feed(key_name=url, url=url, is_root=True))
  return feeds


# Imposed maximum size of a Datastore delete.  Datastore won't let you delete
# more than so many models at once.
MAX_DELETE_BATCH_SIZE = 500


def DeleteInBatches(query_factory, batch_size=100):
  """Deletes model instances in small batches.

  Args:
    query_factory: Closure that produces a db.Query object that fetches
      the model instances to be deleted.
    batch_size: Number of model instances per batch (int)

  Raises:
    ValueError: If batch_size is too large.
  """
  if batch_size > MAX_DELETE_BATCH_SIZE:
    raise ValueError('Batch size cannot exceed %d' % MAX_DELETE_BATCH_SIZE)

  while True:
    query = query_factory()
    models = query.fetch(batch_size)
    if not models:
      return
    db.delete(models)


class CrawlsHandler(webapp.RequestHandler):
  """Displays the Crawl repository."""

  def get(self):
    a_paged_query = paged_query.PagedQuery()
    offset, limit = a_paged_query.ParseRequest(self.request)
    query = cap_schema.Crawl.gql('ORDER BY started DESC')
    crawls_in_progress = []
    crawls_finished = []
    for crawl in query.fetch(limit, offset=offset):
      if crawl.is_done:
        the_list = crawls_finished
      else:
        the_list = crawls_in_progress
      the_list.append(cap_schema.ShadowCrawl(crawl))
    params = dict(locals())
    params.update(a_paged_query.MakeTemplateParams('crawls'))
    params.update(_DEFAULT_PURGE_PARAMS)
    webapp_util.WriteTemplate(self.response, 'crawls.html', params)


class ShardsHandler(webapp.RequestHandler):
  """Displays the CrawlShard repository for a single Crawl."""

  def get(self):
    crawl = _GetCrawlFromRequest(self)
    if not crawl:
      return

    logging.debug('Displaying CrawlShards from Crawl: %s', crawl.key())
    a_paged_query = paged_query.PagedQuery()
    offset, limit = a_paged_query.ParseRequest(self.request)
    shard_query = cap_schema.CrawlShard.gql(
        'WHERE crawl = :1 ORDER BY started DESC', crawl)
    shards = shard_query.fetch(limit, offset=offset)

    params = dict(locals())
    params.update(a_paged_query.MakeTemplateParams(
        'shards', params=dict(crawl=str(crawl.key()))))
    webapp_util.WriteTemplate(self.response, 'shards.html', params)


# Defaults for the purge_crawls.html template, which is included in a few
# other templates.
_DEFAULT_PURGE_PARAMS = dict(purge_days_to_keep=7, purge_batch_size=20)


class FeedsHandler(webapp.RequestHandler):
  """Displays the feed whitelist."""

  def get(self):
    error_msg = self.request.get('error_msg')
    a_paged_query = paged_query.PagedQuery()
    offset, limit = a_paged_query.ParseRequest(self.request)
    query = cap_schema.Feed.gql('WHERE is_root = :1 ORDER BY url', True)
    feeds = [
        cap_schema.ShadowFeed(x) for x in query.fetch(limit, offset=offset)]
    params = dict(feeds=feeds, feed_list_size=len(FEED_LISTS),
                  feed_lists=sorted(FEED_LISTS.keys()))
    params.update(a_paged_query.MakeTemplateParams('feeds'))
    params['error_msg'] = error_msg
    webapp_util.WriteTemplate(self.response, 'feeds.html', params)


class SaveFeedHandler(webapp.RequestHandler):
  """Saves the config data for a Feed."""

  def post(self):
    error_msg = ''
    try:
      self._SaveFeed()
    except (DeadlineExceededError, AssertionError):
      raise
    except Exception, e:
      logging.exception(e)
      error_msg = cgi.escape(str(e), quote=False)

    # Preserve the page.
    a_paged_query = paged_query.PagedQuery()
    offset, limit = a_paged_query.ParseRequest(self.request)
    self.redirect(
        '/feeds?offset=%(offset)d&limit=%(limit)d&error_msg=%(error_msg)s'
        % locals())

  def _SaveFeed(self):
    """Processes the form data to update an existing Feed object.

    Raises:
      SaveFeedError: Any error message to display to the user.
    """
    key = self.request.get('key')
    if not key:
      raise SaveFeedError('No Feed key was specified.')

    is_crawlable = bool(self.request.get('is_crawlable', ''))
    is_root = bool(self.request.get('is_root', ''))
    crawl_period_in_minutes = self.request.get('crawl_period_in_minutes', '-1')
    try:
      crawl_period_in_minutes = int(crawl_period_in_minutes)
    except ValueError:
      raise SaveFeedError(
          'Invalid crawl period: "%s" (must be integer)'
          % crawl_period_in_minutes)

    SaveFeed(key, is_crawlable, is_root, crawl_period_in_minutes)


def SaveFeed(key, is_crawlable, is_root, crawl_period_in_minutes):
  """Updates a single Feed record.

  Args:
    key: Feed key (str)
    is_crawlable: Whether the Feed should be crawled (bool)
    is_root: Whether the Feed should be one of the initial URL's in a crawl
        (bool)
    crawl_period_in_minutes: Minimum amount of time between crawls (int)

  Raises:
    SaveFeedError or db.Error if anything goes wrong.
  """
  logging.info('Saving Feed: %r', locals())
  try:
    key = db.Key(key)
  except db.Error:
    raise SaveFeedError('Invalid Feed key %r' % key)

  feeds = list(cap_schema.Feed.gql('WHERE __key__ = :1', key))
  if not feeds:
    raise SaveFeedError('No Feed found matching key %r' % key)
  if len(feeds) > 1:
    raise SaveFeedError('Multiple Feeds match key %r' % key)
  feed = feeds[0]
  logging.info('Saving Feed %r', feed.url)

  # Populate the Feed object from the form data.
  feed.is_crawlable = is_crawlable
  feed.is_root = is_root
  if crawl_period_in_minutes >= 0:
    feed.crawl_period_in_minutes = crawl_period_in_minutes

  # Save the feed.
  feed.put()


def ClearFeeds():
  """Deletes the Feed Datastore."""
  DeleteInBatches(lambda: db.GqlQuery('SELECT __key__ FROM Feed'))


class ClearFeedsHandler(webapp.RequestHandler):
  """Deletes the Feed Datastore.

  Does NOT delete the corresponding crawls or alerts data.
  """

  def post(self):
    ClearFeeds()
    self.redirect('/feeds')


# TODO(Matt Frantz): Add editing instead of hardcoding the whitelist.
class ResetFeedsHandler(webapp.RequestHandler):
  """Populates the Feed Datastore."""

  def post(self):
    feed_list = self.request.get('feed_list')
    if not feed_list:
      feed_list = 'internal'
    if feed_list not in FEED_LISTS:
      webapp_util.WriteTemplate(
          self.response, 'unknown_feed_list.html',
          dict(unknown_feed_list=feed_list,
               feed_lists=sorted(FEED_LISTS.keys())))
      return
    ResetFeeds(feed_list)
    self.redirect('/feeds')


def ResetFeeds(feed_list):
  """Resets the Feed Datastore to the named list of feeds.

  Any existing Feed entries will not be affected.

  Args:
    feed_list: One of the FEED_LISTS feeds.
  """
  # The design of this function preserves compatibility with Feeds created in
  # previous app versions, in which the Feed key was unspecified.  Because of
  # this constraint, we cannot use Feed.get_or_insert, which otherwise would
  # suffice.

  # Create the new feed list.
  new_feeds = DefaultFeeds(feed_list)
  new_feed_urls = [feed.url for feed in new_feeds]
  # Get any existing Feed objects that match the URL's.
  old_feeds = cap_schema.Feed.gql('WHERE url IN :1', new_feed_urls)
  old_feed_urls = frozenset([feed.url for feed in old_feeds])
  # Make sure we represent each Feed URL.
  for new_feed in new_feeds:
    if new_feed.url not in old_feed_urls:
      new_feed.put()


def _GetCrawlFromRequest(handler):
  """Parses the crawl parameter.

  Args:
    handler: webapp.RequestHandler object

  Returns:
    cap_schema.Crawl object or None if none could be determined.  In that
    case, the response object has already been populated with an error
    screen.
  """
  try:
    crawl_key_str = handler.request.get('crawl')
    if crawl_key_str:
      crawl_key = db.Key(crawl_key_str)
    else:
      crawl_key = _MostRecentCrawl()
      if not crawl_key:
        raise ShardsError('No crawls')

    crawls = cap_schema.Crawl.gql('WHERE __key__ = :1', crawl_key).fetch(1)
    if crawls:
      return crawls[0]
    else:
      raise ShardsError('Unknown Crawl key: %s', crawl_key)

  except AssertionError:
    raise
  except Exception, e:
    logging.exception(e)
    webapp_util.WriteTemplate(
        handler.response, 'invalid_crawl.html',
        dict(crawl_key=crawl_key, error=str(e)))
    return None


class CapsHandler(webapp.RequestHandler):
  """Displays the CapAlert Datastore for the most recent crawl."""

  def get(self):
    crawl = _GetCrawlFromRequest(self)
    if not crawl:
      return

    logging.debug('Displaying CapAlerts from the most recent Crawl: %s',
                  crawl.key())
    a_paged_query = paged_query.PagedQuery()
    offset, limit = a_paged_query.ParseRequest(self.request)
    query = cap_schema.CapAlert.gql(
        'WHERE crawl = :1 ORDER BY __key__', crawl)
    caps = list(query.fetch(limit, offset=offset))

    logging.debug('Cap IDs: %s', ', '.join([str(x.identifier) for x in caps]))
    params = dict(caps=caps, crawl=crawl)
    params.update(a_paged_query.MakeTemplateParams(
        'caps', params=dict(crawl=crawl.key())))
    webapp_util.WriteTemplate(self.response, 'caps.html', params)


def _MostRecentCrawl():
  """Returns the most recent Crawl key.

  Returns:
    Key (str) of the most recently started Crawl, or None if there are no
    crawls.
  """
  keys = db.GqlQuery(
      'SELECT __key__ FROM Crawl ORDER BY started DESC').fetch(1)
  if keys:
    return keys[0]
  else:
    return None


# TODO(Matt Frantz): Make this less dangerous.
class ClearCapsHandler(webapp.RequestHandler):
  """Deletes Cap* data from the Datastore."""

  def get(self):
    self.post()

  def post(self):
    batch_size = int(self.request.get('batch_size', '20'))
    obsolete_models = ['Cap', 'CapInfo', 'CapResource', 'CapArea']
    models = ['CapAlert'] + obsolete_models
    for model in models:
      logging.info('Deleting %s', model)
      DeleteInBatches(lambda: db.GqlQuery('SELECT __key__ FROM %s' % model),
                      batch_size=batch_size)
    self.redirect('/feeds')


def ClearCrawls(batch_size):
  """Deletes all Crawl and CrawlState from the Datastore.

  Args:
    batch_size: Number of model instances per batch (int)
  """
  logging.info('Deleting crawl shards')
  DeleteInBatches(lambda: db.GqlQuery('SELECT __key__ FROM CrawlShard'),
                  batch_size=batch_size)
  logging.info('Deleting crawls')
  DeleteInBatches(lambda: db.GqlQuery('SELECT __key__ FROM Crawl'),
                  batch_size=batch_size)


# TODO(Matt Frantz): Make this less dangerous.
class ClearCrawlsHandler(webapp.RequestHandler):
  """Deletes Crawl data from the Datastore."""

  def get(self):
    self.post()

  def post(self):
    batch_size = int(self.request.get('batch_size', '20'))
    ClearCrawls(batch_size)
    self.redirect('/crawls')


class PurgeCrawlsHandler(webapp.RequestHandler):
  """Deletes Crawl and Cap data for old crawls."""

  def get(self):
    self.post()

  def post(self):
    # Read CGI params, defaulting to hardcoded defaults.  These variable names
    # align with the purge_crawls.html template parameters.
    purge_days_to_keep = int(self.request.get(
        'days_to_keep', str(_DEFAULT_PURGE_PARAMS['purge_days_to_keep'])))
    purge_batch_size = int(self.request.get(
        'batch_size', str(_DEFAULT_PURGE_PARAMS['purge_batch_size'])))

    # Avoid purging the most recent crawls per feed.
    last_crawls = cap_schema.LastCrawls()
    logging.info('Saving most recent crawls: %s', [str(x) for x in last_crawls])
    crawls_purged, error = PurgeCrawls(
        purge_days_to_keep, purge_batch_size, last_crawls)
    webapp_util.WriteTemplate(self.response, 'crawls_purged.html', locals())


def PurgeCrawls(days_to_keep, batch_size, last_crawls,
                _now=datetime.datetime.now):
  """Purge Crawl and Cap data.

  Args:
    days_to_keep: Minimum number of days to keep (int)
    batch_size: Number of model instances per batch (int)
    last_crawls: Set of Crawl keys that should not be purged (set of str)
    _now: dependency injection of clock function that returns
        datetime.datetime object.

  Returns:
    (crawls_purged, error)
    crawls_purged: Number of crawls purged.
    error: Description of any error that occurred.
  """
  # Calculate the cutoff date from now.
  cutoff_date = _now() - datetime.timedelta(days=days_to_keep)
  logging.info('Purging crawls before %s', cutoff_date)
  # Get the oldest Crawl that's not blacklisted.
  query = db.GqlQuery(
      'SELECT __key__ FROM Crawl '
      'WHERE started < :cutoff_date '
      'ORDER BY started', cutoff_date=cutoff_date)
  crawls_purged = 0
  error = None
  try:
    while True:
      crawl_keys = list(query.fetch(1))
      if crawl_keys:
        crawl_key = crawl_keys[0]
        if crawl_key in last_crawls:
          # TODO(Matt Frantz): Figure out how to continue purging when we hit a
          # blacklisted crawl.
          logging.info('Cannot purge crawl %s because it is the most recent '
                       'crawl for at least one feed.', crawl_key)
          break
        else:
          PurgeCrawl(crawl_key, batch_size)
          crawls_purged += 1
      else:
        logging.info('No more crawls to purge.')
        break

  except AssertionError:
    raise
  except DeadlineExceededError:
    # Suppress the deadline exceeded so we can write a response.
    error = 'Deadline exceeded'
  except Exception, e:
    logging.exception(e)
    error = str(e)

  return crawls_purged, error


def PurgeCrawl(crawl_key, batch_size):
  """Purge all data associated with a crawl.

  Args:
    crawl_key: Model key for the Crawl (db.Key)
    batch_size: Number of model instances per batch (int)
  """
  logging.info('Purging crawl %s', crawl_key)
  obsolete_models = ['CapResource', 'CapArea', 'CapInfo', 'Cap']
  models = ['CapAlert', 'CrawlShard'] + obsolete_models
  for model in models:
    logging.info('Purging %s for crawl %s', model, crawl_key)
    query = lambda: db.GqlQuery(
        'SELECT __key__ FROM %s WHERE crawl = :1' % model, crawl_key)
    DeleteInBatches(query, batch_size=batch_size)

  # Delete the Crawl itself.
  logging.info('Deleting crawl %s', crawl_key)
  DeleteInBatches(
      lambda: db.GqlQuery('SELECT __key__ FROM Crawl WHERE __key__ = :1',
                          crawl_key))


application = webapp.WSGIApplication(
    [('/caps', CapsHandler),
     ('/clearcaps', ClearCapsHandler),
     ('/clearcrawls', ClearCrawlsHandler),
     ('/clearfeeds', ClearFeedsHandler),
     ('/crawls', CrawlsHandler),
     ('/feeds', FeedsHandler),
     ('/purgecrawls', PurgeCrawlsHandler),
     ('/resetfeeds', ResetFeedsHandler),
     ('/savefeed', SaveFeedHandler),
     ('/shards', ShardsHandler),
     ],
    debug=True)


def main():
  run_wsgi_app(application)


if __name__ == '__main__':
  main()
