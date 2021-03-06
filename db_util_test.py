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

"""Tests for db_util."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

from google3.pyglib import app
from google3.testing.pybase import googletest
from google3.dotorg.gongo.appengine_cap2kml import db_util


class DbUtilTest(googletest.TestCase):
  """Tests for db_util."""

  # TODO(Matt Frantz): Write these tests.


def main(unused_argv):
  googletest.main()


if __name__ == '__main__':
  app.run()
