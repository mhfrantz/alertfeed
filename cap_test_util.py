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

"""Utilities for writing unit tests that involve the CAP AppEngine Datastore.

These functions generate and query test data from the models defined in
cap_schema.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

from google3.dotorg.gongo.appengine_cap2kml import cap_schema


def NewCrawls(num_crawls, now):
  """Generates Crawl models in the Datastore.

  All Crawls will be completed, and will use timestamps from now.

  Args:
    num_crawls: Number of crawls to produce (int)
    now: datetime.datetime factory (e.g. fake_clock.FakeNow object)

  Returns:
    List of cap_schema.Crawl objects, already saved.
  """
  crawls = []
  for i in xrange(num_crawls):
    crawl = cap_schema.Crawl()
    crawl.started = now()
    crawl.finished = now()
    crawl.is_done = True
    crawl.put()
    crawls.append(crawl)

  return crawls


def NewShards(num_shards, crawl):
  """Generates shard objects for testing.

  Args:
    num_shards: Number of shards to create (int).
    crawl: cap_schema.Crawl to reference.

  Returns:
    List containing num_shards cap_schema.CrawlShard objects.
  """
  shards = []
  for i in xrange(num_shards):
    shard = NewShard('http://%d' % i, crawl)
    shards.append(shard)

  return shards


def NewShard(url, crawl, feed=None):
  """Generates a shard object for testing.

  Args:
    url: URL for the shard (str)
    crawl: cap_schema.Crawl to reference.
    feed: cap_schema.Feed to reference, or None to leave it unreferenced.

  Returns:
    cap_schema.CrawlShard object, already saved.
  """
  shard = cap_schema.CrawlShard()
  shard.crawl = crawl
  shard.url = url
  if feed:
    shard.feed = feed
  shard.put()
  return shard


def NewFeeds(num_feeds):
  """Generates Feed models in the Datastore.

  Each Feed will be assigned a unique, deterministic URL.

  Args:
    num_feeds: Number of feeds to produce (int)

  Returns:
    List of cap_schema.Feed objects, already saved.
  """
  feeds = []
  for i in xrange(num_feeds):
    feed = cap_schema.Feed(url='http://feed%d' % i)
    feed.put()
    feeds.append(feed)
  return feeds


def GetFeed(key):
  """Queries the Datastore for a single Feed.

  Args:
    key: db.Key representing the Feed

  Returns:
    A single cap_schema.Feed object, or None if none can be found.
  """
  return cap_schema.Feed.get(key)
