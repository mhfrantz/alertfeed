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

"""Tests for cap_parse_db."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import datetime

import google3
import iso8601
import cap as caplib
import mox

from google3.pyglib import app
from google3.testing.pybase import googletest
from google3.dotorg.gongo.appengine_cap2kml import cap_parse_db
from google3.dotorg.gongo.appengine_cap2kml import db_test_util
from google3.dotorg.gongo.appengine_cap2kml import model_parser


class CapParseDbTestBase(mox.MoxTestBase, db_test_util.DbTestBase):
  """Base class for all cap_parse_db unit tests."""

  def setUp(self):
    super(CapParseDbTestBase, self).setUp()
    # Stub out anything that we never want to call for real.
    self.mox.StubOutWithMock(cap_parse_db, 'logging')
    self.mox.StubOutWithMock(model_parser, 'logging')


class MakeDbAlertFromMemTest(CapParseDbTestBase):
  """Tests for cap_parse_db.MakeDbAlertFromMem."""

  def setUp(self):
    super(MakeDbAlertFromMemTest, self).setUp()
    self.alert_mem = caplib.Alert()

  def _MakeDbAlertFromMem(self):
    """Turns the internal memory Alert into a Datastore Alert.

    Preconditions:
      self.alert_mem is populated with a caplib.Alert object.

    Returns:
      cap_schema.CapAlert object, populated and saved.
    """
    alert_db = cap_parse_db.MakeDbAlertFromMem(self.alert_mem)
    alert_db.put()
    return alert_db

  def testIdentifier(self):
    self.mox.ReplayAll()

    self.alert_mem.identifier = 'id1'
    alert_db = self._MakeDbAlertFromMem()
    self.assertEquals('id1', alert_db.identifier)

  def testSender(self):
    self.mox.ReplayAll()

    self.alert_mem.sender = 'sender1'
    alert_db = self._MakeDbAlertFromMem()
    self.assertEquals('sender1', alert_db.sender)

  def testSent(self):
    self.mox.ReplayAll()

    sent = datetime.datetime(2009, 9, 11, 12, 34, 56, tzinfo=iso8601.UTC)
    self.alert_mem.sent = sent
    alert_db = self._MakeDbAlertFromMem()
    self.assertEquals(sent, alert_db.sent)

  def testStatus(self):
    self.mox.ReplayAll()

    self.alert_mem.status = 'Actual'
    alert_db = self._MakeDbAlertFromMem()
    self.assertEquals('Actual', alert_db.status)

  def testMsgType(self):
    self.mox.ReplayAll()

    self.alert_mem.msgType = 'Alert'
    alert_db = self._MakeDbAlertFromMem()
    self.assertEquals('Alert', alert_db.msgType)

  def testSource(self):
    self.mox.ReplayAll()

    self.alert_mem.source = 'foo'
    alert_db = self._MakeDbAlertFromMem()
    self.assertEquals('foo', alert_db.source)

  def testRestriction(self):
    self.mox.ReplayAll()

    self.alert_mem.restriction = 'foo'
    alert_db = self._MakeDbAlertFromMem()
    self.assertEquals('foo', alert_db.restriction)

  def testAddresses(self):
    self.mox.ReplayAll()

    self.alert_mem.addresses = 'foo'
    alert_db = self._MakeDbAlertFromMem()
    # Should be ignored.

  def testCode(self):
    self.mox.ReplayAll()
    codes = ['foo', 'bar']
    for code in codes:
      self.alert_mem.codes.append(code)
    alert_db = self._MakeDbAlertFromMem()
    self.assertListEqual(codes, list(alert_db.code))

  def testNote(self):
    self.mox.ReplayAll()

    self.alert_mem.note = 'foo'
    alert_db = self._MakeDbAlertFromMem()
    # Should be ignored.

  def testReference(self):
    self.mox.ReplayAll()
    references = ['foo,1,2009-09-11T12:34:56+00:00',
                  'bar,1,2010-10-12T12:34:56+00:00']
    for reference in references:
      self.alert_mem.references.append(caplib.Reference(reference))
    alert_db = self._MakeDbAlertFromMem()
    self.assertListEqual(references, list(alert_db.references))

  def testIncidents(self):
    self.mox.ReplayAll()

    self.alert_mem.incidents = 'foo'
    alert_db = self._MakeDbAlertFromMem()
    # Should be ignored.

  def testInfos(self):
    self.mox.ReplayAll()

    info = caplib.Info()
    self.alert_mem.info.append(info)
    info.language = 'Pig Latin'
    info.category.append('Geo')
    info.event = 'Something happened.'
    info.response.append('Evacuate')
    info.response.append('Shelter')
    info.urgency = 'Immediate'
    info.severity = 'Severe'
    info.certainty = 'Observed'
    info.audience = 'Everyone'
    info.effective = datetime.datetime(2001, 9, 11, tzinfo=iso8601.UTC)
    info.onset = datetime.datetime(2001, 9, 12, tzinfo=iso8601.UTC)
    info.expires = datetime.datetime(2009, 1, 21, tzinfo=iso8601.UTC)
    info.senderName = 'Elvis'
    info.headline = 'Pinedale Shopping Mall has been Bombed by Live Turkeys'
    info.description = 'Just what it sounds like.'
    info.instruction = 'Duck and cover.'
    info.web = 'http://turkey.com'
    info.contact = 'Tom Thumb'

    info = caplib.Info()
    self.alert_mem.info.append(info)
    info.language = 'Love'
    info.category.append('Met')
    info.category.append('Infra')
    info.event = 'Something else will happen.'
    info.response.append('Prepare')
    info.urgency = 'Future'
    info.severity = 'Minor'
    info.certainty = 'Possible'
    info.audience = 'Nobody'
    info.effective = datetime.datetime(2011, 9, 11, tzinfo=iso8601.UTC)
    info.onset = datetime.datetime(2011, 9, 12, tzinfo=iso8601.UTC)
    info.expires = datetime.datetime(2019, 1, 21, tzinfo=iso8601.UTC)
    info.senderName = 'Priscilla'
    info.headline = 'The King is Dead'
    info.description = 'Long live the king.'
    info.instruction = 'Rejoice.'
    info.web = 'http://leftthebuilding.com'
    info.contact = 'Les Nesman'

    alert_db = self._MakeDbAlertFromMem()
    self.assertListEqual(['Pig Latin', 'Love'], alert_db.language)
    self.assertListEqual(['Geo', 'Met', 'Infra'], alert_db.category)
    # TODO(Matt Frantz): Check "event" when we index it.
    self.assertListEqual(['Evacuate', 'Shelter', 'Prepare'],
                         alert_db.responseType)
    self.assertListEqual(['Immediate', 'Future'], alert_db.urgency)
    self.assertListEqual(['Severe', 'Minor'], alert_db.severity)
    self.assertListEqual(['Observed', 'Possible'], alert_db.certainty)
    self.assertListEqual(['Everyone', 'Nobody'], alert_db.audience)
    # TODO(Matt Frantz): Check "eventCode" when we index it.
    self.assertListEqual(
        [caplib.Effective(datetime.datetime(2001, 9, 11, tzinfo=iso8601.UTC)),
         caplib.Effective(datetime.datetime(2011, 9, 11, tzinfo=iso8601.UTC))],
        alert_db.effective)
    self.assertListEqual(
        [caplib.Effective(datetime.datetime(2001, 9, 12, tzinfo=iso8601.UTC)),
         caplib.Effective(datetime.datetime(2011, 9, 12, tzinfo=iso8601.UTC))],
        alert_db.onset)
    self.assertListEqual(
        [caplib.Effective(datetime.datetime(2009, 1, 21, tzinfo=iso8601.UTC)),
         caplib.Effective(datetime.datetime(2019, 1, 21, tzinfo=iso8601.UTC))],
        alert_db.expires)
    self.assertListEqual(['Elvis', 'Priscilla'], alert_db.senderName)
    # TODO(Matt Frantz): Check "headline" when we index it.
    # TODO(Matt Frantz): Check "description" when we index it.
    # TODO(Matt Frantz): Check "instruction" when we index it.
    self.assertListEqual(['http://turkey.com', 'http://leftthebuilding.com'],
                         alert_db.web)
    self.assertListEqual(['Tom Thumb', 'Les Nesman'], alert_db.contact)

  def testResource(self):
    info = caplib.Info()
    self.alert_mem.info.append(info)

    resource = caplib.Resource()
    info.resource.append(resource)
    resource.description = 'Resource #1'
    resource.mimetype = 'text/plain'
    resource.size = 123
    resource.uri = 'http://foo'
    resource.deref = 'foo'
    resource.digest = caplib.Digest.string('foo')

    resource = caplib.Resource()
    info.resource.append(resource)
    resource.description = 'Resource #2'
    resource.mimetype = 'text/html'
    resource.size = 456
    resource.uri = 'http://bar'
    resource.deref = 'bar'
    resource.digest = caplib.Digest.string('bar')

    alert_db = self._MakeDbAlertFromMem()
    self.assertListEqual(['Resource #1', 'Resource #2'], alert_db.resourceDesc)
    self.assertListEqual(['text/plain', 'text/html'], alert_db.mimeType)
    self.assertListEqual([123, 456], alert_db.size)
    self.assertListEqual(['http://foo', 'http://bar'], alert_db.uri)
    # TODO(Matt Frantz): Check "deref" when we index it.
    # TODO(Matt Frantz): Check "digest" when we index it.

  @staticmethod
  def _MakePolygon(*coordinates):
    """Makes a polygon from a list of coordinate tuples.

    Args:
      coordinates: latitude, longitude pairs (float, float)

    Returns:
      caplib.Polygon object
    """
    # Make sure the last point equals the first point.
    coordinates = list(coordinates) + [coordinates[0]]
    return caplib.Polygon([caplib.Point(*x) for x in coordinates])

  def testArea(self):
    info = caplib.Info()
    self.alert_mem.info.append(info)

    area = caplib.Area()
    info.area.append(area)
    area.description = 'Area #1'
    area.polygon.append(
        self._MakePolygon((1.23, 4.56), (2.34, 5.67), (3.45, 6.78)))
    area.polygon.append(
        self._MakePolygon((-1.2, -3.4), (-2.3, -4.5), (-3.4, -5.6)))
    area.circle.append(caplib.Circle(caplib.Point(1.2, 3.4), 5.6))
    area.circle.append(caplib.Circle(caplib.Point(7.8, 9.0), 2.1))
    # TODO(Matt Frantz): Test "geocode" when we index it.
    area.altitude = 5.1
    area.ceiling = 700

    area = caplib.Area()
    info.area.append(area)
    area.description = 'Area #2'
    area.polygon.append(
        self._MakePolygon((-1.23, -4.56), (-2.34, -5.67), (-3.45, -6.78)))
    area.circle.append(caplib.Circle(caplib.Point(-1.2, -3.4), 6.5))
    # TODO(Matt Frantz): Test "geocode" when we index it.
    area.altitude = 6.2
    area.ceiling = 14.92

    alert_db = self._MakeDbAlertFromMem()
    # TODO(Matt Frantz): Check "areaDesc" when we index it.
    # TODO(Matt Frantz): Check "polygon" when we index it.
    # TODO(Matt Frantz): Check "circle" when we index it.
    self.assertListEqual([5.1, 6.2], alert_db.altitude)
    self.assertListEqual([700, 14.92], alert_db.ceiling)


def main(unused_argv):
  googletest.main()


if __name__ == '__main__':
  app.run()
