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

"""Tests for cap_parse_mem."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import os.path

import google3

import cap as caplib

from google3.pyglib import app
from google3.pyglib import resources
from google3.testing.pybase import googletest
from google3.dotorg.gongo.appengine_cap2kml import cap_parse_mem


class CapParseMemTest(googletest.TestCase):

  def setUp(self):
    self.parser = cap_parse_mem.MemoryCapParser()
    self.new_alert_model = lambda: caplib.Alert()

  def _ReadTestData(self, basename):
    """Returns the contents of the specified test data file.

    Args:
      basename: Name of a file in the testdata directory.

    Returns:
      Contents of the file (str)
    """
    return resources.GetResource(os.path.join(
        'google3', 'dotorg', 'gongo', 'appengine_cap2kml', 'testdata',
        basename))

  def testAquilaCap2(self):
    alert, errors = self.parser.MakeAlert(self.new_alert_model,
                                          self._ReadTestData('aquila_cap2.xml'))
    self.assertListEqual(errors, [])
    self.assertEquals(alert.identifier, 'DIPVVF-20090409-1001-3')
    self.assertEquals(alert.sender, 'dipartimento-vigilifuoco.it')

    self.assertEquals(len(alert.info), 1)
    info = list(alert.info)[0]
    self.assertListEqual(list(info.category), ['Infra'])
    self.assertEquals(info.urgency, 'Unknown')
    self.assertEquals(info.severity, 'Unknown')
    self.assertEquals(info.certainty, 'Observed')
    self.assertEquals(info.audience, 'original')
    self.assertEquals(info.senderName, 'Dipartimento Vigili del Fuoco')
    self.assertEquals(info.headline, 'TEST 2')
    self.assertEquals(info.description, 'Test 2 description')
    self.assertEquals(info.web, 'http://www.vigilfuoco.it/')

    self.assertEquals(len(info.area), 1)
    area = list(info.area)[0]
    self.assertEquals(area.description,
                      'Via Pietro Aldi, 21, 00125 Roma, Italia')
    self.assertListEqual(
        list(area.circle),
        [caplib.Circle(caplib.Point(41.7806015, 12.3580999), 0.01)])

  # TODO(Matt Frantz): Test more of the sample CAP files that we have
  # accumulated.

  # TODO(Matt Frantz): Write unit tests for cap_parse_mem.


def main(unused_argv):
  googletest.main()


if __name__ == '__main__':
  app.run()
