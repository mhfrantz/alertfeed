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

"""Tests for cap_schema_mem."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

from google3.pyglib import app
from google3.testing.pybase import googletest
from google3.dotorg.gongo.appengine_cap2kml import cap_schema_mem
from google3.dotorg.gongo.appengine_cap2kml import web_query


class CapSchemaMemTest(googletest.TestCase):
  """Tests for cap_schema_mem."""

  def setUp(self):
    scalar_ops = web_query.Operators.SCALAR_ALL
    self.equals = web_query.Operators.SCALAR_EQUALS

  def testShadowAlert_withInfoFilter(self):
    predicate = web_query.SimpleComparisonPredicate(
        'CapAlert', 'urgency', 'Future', self.equals)
    query = web_query.Query([predicate])
    alert = cap_schema_mem.ShadowAlert(query=query)

    info_data = [('Future', 'OK 1'),
                 ('Past', 'BAD 1'),
                 ('Future', 'OK 2'),
                 ('Past', 'BAD 2'),
                 ]
    for urgency, headline in info_data:
      info = cap_schema_mem.ShadowInfo()
      info.urgency = urgency
      info.headline = headline
      alert.info.append(info)

    self.assertListEqual([x.headline for x in alert.info], ['OK 1', 'OK 2'])

  def testShadowInfo_withAreaFilter(self):
    predicate = web_query.SimpleComparisonPredicate(
        'CapAlert', 'areaDesc', 'foo', self.equals)
    query = web_query.Query([predicate])
    info = cap_schema_mem.ShadowInfo(query=query)

    area_data = [('foo', 12.0),
                 ('bar', 34.0),
                 ('foo', 56.0),
                 ('bar', 78.0),
                 ]
    for area_desc, altitude in area_data:
      area = cap_schema_mem.ShadowArea()
      area.areaDesc = area_desc
      area.altitude = altitude
      info.area.append(area)

    self.assertListEqual([x.altitude for x in info.area], [12.0, 56.0])

  def testShadowInfo_withResourceFilter(self):
    predicate = web_query.SimpleComparisonPredicate(
        'CapAlert', 'resourceDesc', 'foo', self.equals)
    query = web_query.Query([predicate])
    info = cap_schema_mem.ShadowInfo(query=query)

    resource_data = [('foo', 12),
                     ('bar', 34),
                     ('bar', 56),
                     ('foo', 78)]
    for resource_desc, size in resource_data:
      resource = cap_schema_mem.ShadowResource()
      resource.resourceDesc = resource_desc
      resource.size = size
      info.resource.append(resource)

    self.assertListEqual([x.size for x in info.resource], [12, 78])


def main(unused_argv):
  googletest.main()


if __name__ == '__main__':
  app.run()
