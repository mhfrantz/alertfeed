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

"""Datastore models for storing CAP.

In addition to direct subclasses of db.Model, this module defines Shadow*
classes that handle dereferencing of types that are lists of references, as
well as derived properties that are available for Django templates.  For
example, ShadowCrawl is a subclass of Crawl, and it adds the 'feeds' derived
property.

References to the 'CAP 1.1' standard refer to sections in this document:
http://www.oasis-open.org/committees/download.php/14759/emergency-CAPv1.1.pdf
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import datetime

try:
  # google3
  from google3.apphosting.ext import db
  from google3.pyglib import logging

  from google3.dotorg.gongo.appengine_cap2kml import db_util
  from google3.dotorg.gongo.appengine_cap2kml import web_query

except ImportError:
  import logging

  from google.appengine.ext import db

  import db_util
  import web_query


# TODO(Matt Frantz): Decide which attributes should be TextProperty and which
# should be StringProperty.  TextProperty is unlimited length, but can't be an
# index key.  StringProperty is <500 characters, but can be indexed (and thus
# filtered in a query).


class Crawl(db.Model):
  """Persistent state of a single crawl."""
  is_done = db.BooleanProperty(default=False)
  started = db.DateTimeProperty()
  finished = db.DateTimeProperty()
  feed_urls = db.StringListProperty()


DEFAULT_CRAWL_PERIOD_IN_MINUTES = 60
DEFAULT_CRAWL_PERIOD = datetime.timedelta(
    minutes=DEFAULT_CRAWL_PERIOD_IN_MINUTES)


class Feed(db.Model):
  """Site containing CAP data."""
  url = db.StringProperty()
  is_crawlable = db.BooleanProperty(default=True)
  is_root = db.BooleanProperty(default=True)
  crawl_period_in_minutes = db.IntegerProperty(
      default=DEFAULT_CRAWL_PERIOD_IN_MINUTES)
  last_crawl = db.Reference(Crawl)

  def __str__(self):
    return str(db_util.ModelAsDict(Feed, self))


class CapAlert(db.Model):
  """CAP file from a feed."""
  crawl = db.Reference(Crawl)
  feed = db.Reference(Feed)
  url = db.StringProperty()
  text = db.TextProperty()
  parse_errors = db.ListProperty(db.Text)
  # CAP alert properties that we care about.  (CAP 1.1 sec 3.2.1)
  identifier = db.StringProperty()
  sender = db.StringProperty()
  sent = db.DateTimeProperty()
  status = db.StringProperty()  # enum
  msgType = db.StringProperty()  # enum
  source = db.StringProperty()
  scope = db.StringProperty()  # enum
  restriction = db.StringProperty()
  # TODO(Matt Frantz): Save "addresses" when Datastore has text search.
  code = db.StringListProperty()
  # TODO(Matt Frantz): Save "note" when Datastore has text search.
  references = db.StringListProperty()
  # TODO(Matt Frantz): Save "incidents" when Datastore has text search.

  # Info.
  language = db.StringListProperty()
  category = db.StringListProperty()  # enum
  # TODO(Matt Frantz): Save "event" when Datastore has text search.
  responseType = db.StringListProperty()  # enum
  urgency = db.StringListProperty()  # enum
  severity = db.StringListProperty()  # enum
  certainty = db.StringListProperty()  # enum
  audience = db.StringListProperty()
  # TODO(Matt Frantz): Save "eventCode" tag/value pairs.
  effective = db.ListProperty(datetime.datetime)
  onset = db.ListProperty(datetime.datetime)
  expires = db.ListProperty(datetime.datetime)
  senderName = db.StringListProperty()
  # TODO(Matt Frantz): Save "headline" when Datastore has text search.
  # TODO(Matt Frantz): Save "description" when Datastore has text search.
  # TODO(Matt Frantz): Save "instruction" when Datastore has text search.
  web = db.StringListProperty()  # URI
  contact = db.StringListProperty()
  # TODO(Matt Frantz): Save "parameter" tag/value pairs.
  # TODO(Matt Frantz): Save "eventCode".

  # Resource.
  resourceDesc = db.StringListProperty()
  mimeType = db.StringListProperty()
  size = db.ListProperty(long)  # unit?
  uri = db.StringListProperty()  # URI
  # TODO(Matt Frantz): Save "derefUri"?
  # TODO(Matt Frantz): Save "digest"?

  # Area.
  # TODO(Matt Frantz): Save "areaDesc" when Datastore has text search.
  # TODO(Matt Frantz): Save "polygon" in an indexable way.
  # TODO(Matt Frantz): Save "circle" in an indexable way.
  # TODO(Matt Frantz): Save "geocode" tag/value pairs?
  altitude = db.ListProperty(float)
  ceiling = db.ListProperty(float)

  def __str__(self):
    return str(db_util.ModelAsDict(Cap, self))


class CrawlShard(db.Model):
  """Single atom of crawl work, which is a URL."""
  crawl = db.Reference(Crawl)
  feed = db.Reference(Feed)
  url = db.TextProperty()
  is_done = db.BooleanProperty(default=False)
  # When is_done is True, then the following may be populated.
  started = db.DateTimeProperty()
  finished = db.DateTimeProperty()
  error = db.TextProperty()
  parse_errors = db.ListProperty(db.Text)


class ShadowCrawl(Crawl):
  """Shadow for Crawl that provides derived properties."""

  def __init__(self, crawl):
    """Initializes a ShadowCrawl from a Crawl.

    Args:
      crawl: Crawl object
    """
    super(ShadowCrawl, self).__init__(**db_util.ModelAsDict(Crawl, crawl))
    self.__feeds = None
    self.__shards = None
    self.__shards_remaining = None
    self.__key = crawl.key()

  def key(self):
    return self.__key

  @property
  def feeds(self):
    """Returns the set of feeds involved in this crawl.

    Returns:
      Set of Feed objects.
    """
    if not self.__feeds:
      feeds = set()
      for shard in self.shards:
        feed = db_util.SafelyDereference(shard, 'feed')
        if feed:
          feeds.add(feed)
      self.__feeds = frozenset(feeds)
    return self.__feeds

  @property
  def shards(self):
    """Returns all shards for this crawl.

    Returns:
      List of CrawlShard objects.
    """
    if not self.__shards:
      self.__shards = DereferenceFilterAndShadow(self, 'CrawlShard',
                                                 shadow_class=ShadowCrawlShard)
    return self.__shards


class ShadowCrawlShard(CrawlShard):
  """Shadow for CrawlShard that provides derived properties."""

  def __init__(self, crawl_shard):
    """Initializes a ShadowCrawlShard from a CrawlShard.

    Args:
      crawl_shard: CrawlShard object
    """
    super(ShadowCrawlShard, self).__init__(
        **db_util.ModelAsDict(CrawlShard, crawl_shard))


class ShadowFeed(Feed):
  """Shadow for Feed that provides derived properties."""

  def __init__(self, feed):
    """Initializes a ShadowFeed from a Feed.

    Args:
      feed: Feed object
    """
    super(ShadowFeed, self).__init__(**db_util.ModelAsDict(Feed, feed))
    self.__key = feed.key()

  def key(self):
    return self.__key


def _FilterModels(model_name, models, web_query):
  for model in models:
    if web_query.PermitsModel(model_name, model):
      yield model


def _ShadowModels(shadow_class, models):
  for model in models:
    shadow = shadow_class(model)
    yield shadow


def DereferenceFilterAndShadow(referenced_model, subordinate_model_name,
                               shadow_class=None, web_query=None):
  """Dereferences a set of keys, filters and shadows the resulting objects.

  Args:
    referenced_model: Model object being referenced.  It must have a standard
        back-pointer property for the subordinate_model_name.
    subordinate_model_name: Name of the model of the dereferenced objects.
        Model class must include a ReferenceProperty that refers to the
        referenced_model.
    shadow_class: Class object for the shadow of the dereferenced objects,
        or None for no shadowing.
    query: web_query.Query object or None for no filter.

  Returns:
    List of the subordinate models or their shadows.
  """
  # Use the back-pointers to dereference.
  subordinate_models = db_util.SafelyDereference(
      referenced_model,
      '%s_set' % subordinate_model_name.lower())
  if not subordinate_models:
    return []
  # Apply any web query.
  if web_query:
    subordinate_models = _FilterModels(
        subordinate_model_name, subordinate_models, web_query)
  # Wrap in the shadow class.
  if shadow_class:
    subordinate_models = _ShadowModels(shadow_class, subordinate_models)
  return list(subordinate_models)


def LastCrawls():
  """Returns the last completed crawl for each feed.

  Returns:
    set of Crawl objects, empty if there are no crawls
  """
  # We only need to look at root feeds, because the children are only
  # crawled when their root is crawled.
  query = Feed.gql('WHERE is_root = :1', True)
  crawls = set()
  limit = 100
  offset = 0
  while True:
    feeds = query.fetch(limit, offset=offset)
    offset += limit
    if feeds:
      for feed in feeds:
        crawl = feed.last_crawl
        if crawl:
          crawls.add(crawl.key())
    else:
      return crawls


# TODO(Matt Frantz): Remove obsolete models, which are sticking around only to
# allow them to be purged.


class Cap(db.Model):
  crawl = db.Reference(Crawl)


class CapInfo(db.Model):
  crawl = db.Reference(Crawl)


class CapArea(db.Model):
  crawl = db.Reference(Crawl)


class CapResource(db.Model):
  crawl = db.Reference(Crawl)
