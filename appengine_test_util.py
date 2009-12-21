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

"""Utilities for writing unit tests that involve the AppEngine.

Based on code from the following post on gist.github, which demonstrate a set
of base classes that are designed to support the various AppEngine components:

https://gist.github.com/186251/6f1434f1ea0ccf5f618cbf3ac91b8dde07156977
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import os
import time

try:
  from google3.apphosting.api import apiproxy_stub_map
  from google3.testing.pybase import googletest as unittest
except ImportError:
  import unittest
  from google.appengine.api import apiproxy_stub_map


class AppEngineTestBase(unittest.TestCase):
  """Base class that allows unit tests to use a fake AppEngine.

  Attributes:
    apiproxy_stub_map: apiproxy_stub_map.APIProxyStubMap object
    app_id: Application ID (str)
  """

  def setUp(self):
    self.apiproxy_stub_map = apiproxy_stub_map.APIProxyStubMap()
    apiproxy_stub_map.apiproxy = self.apiproxy_stub_map
    self.app_id = 'test_app'
    os.environ['APPLICATION_ID'] = self.app_id
