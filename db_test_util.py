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

"""Utilities for writing unit tests that involve the AppEngine Datastore.

Based on code from the following post on gist.github, which demonstrate a set
of base classes that are designed to support the various AppEngine components:

https://gist.github.com/186251/6f1434f1ea0ccf5f618cbf3ac91b8dde07156977
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

try:
  from google3.apphosting.api import datastore_file_stub
  from google3.apphosting.ext import db
  from google3.dotorg.gongo.appengine_cap2kml import appengine_test_util
except ImportError:
  import appengine_test_util
  from google.appengine.api import datastore_file_stub
  from google.appengine.ext import db


class DbTestBase(appengine_test_util.AppEngineTestBase):
  """Base class that allows unit tests to use Datastore."""

  def setUp(self):
    super(DbTestBase, self).setUp()
    self.__datastore_stub = datastore_file_stub.DatastoreFileStub(
        self.app_id, '/dev/null', '/dev/null')
    self.__datastore_stub.Clear()
    self.apiproxy_stub_map.RegisterStub('datastore_v3', self.__datastore_stub)
