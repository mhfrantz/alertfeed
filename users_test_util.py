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

"""Utilities for writing unit tests that involve the AppEngine users API.

Based on code from the following post on gist.github, which demonstrate a set
of base classes that are designed to support the various AppEngine components:

https://gist.github.com/186251/6f1434f1ea0ccf5f618cbf3ac91b8dde07156977
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import os

try:
  from google3.apphosting.api import user_service_stub
  from google3.dotorg.gongo.appengine_cap2kml import appengine_test_util
except ImportError:
  import appengine_test_util
  from google.appengine.api import user_service_stub


class UsersTestBase(appengine_test_util.AppEngineTestBase):
  """Base class that allows unit tests to use the 'user' module."""

  def setUp(self):
    super(UsersTestBase, self).setUp()
    self.__user_stub = user_service_stub.UserServiceStub()
    self.apiproxy_stub_map.RegisterStub('user', self.__user_stub)
    self.SetUser('foo@bar.com')

  def SetUser(self, user_email, user_is_admin='0'):
    """Specifies the fake user that will appear to be running the unit tests.

    Args:
      user_email: Email of the fake user (str)
      user_is_admin: If '1', the user has admin privileges; if '0', it does
          not.
    """
    os.environ['USER_EMAIL'] = user_email
    os.environ['USER_IS_ADMIN'] = user_is_admin
