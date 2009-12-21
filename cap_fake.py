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

"""Fake data that is built in to the CAP mirror."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'


def _FakeFeedIndex1():
  """Returns the list of URL's associated with _FAKE_FEED_URL_1_."""
  return ['testdata/fake1_cap%d.xml' % (x + 1) for x in xrange(3)]


def _FakeFeedIndex2():
  """Returns the list of URL's associated with _FAKE_FEED_URL_2_."""
  return ['testdata/fake2_cap%d.xml' % (x + 1) for x in xrange(5)]


# If a feed refers to any of these URL's, the CAP data will be faked using the
# specified factory method.
FAKE_FEED_URLS = {
    '_FAKE_FEED_URL_1_': _FakeFeedIndex1,
    '_FAKE_FEED_URL_2_': _FakeFeedIndex2,
    }
