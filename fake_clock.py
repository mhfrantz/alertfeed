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

"""Fake clock for unit test injection."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import datetime


class FakeNow(object):
  """Fake clock for unit test injection as datetime.datetime.now.

  Attributes:
    now: Next value to return (datetime.datetime)
    increment: Amount to increment each call (datetime.timedelta)
  """

  DEFAULT_NOW = datetime.datetime(1970, 1, 1, 0, 0, 0)
  DEFAULT_INCREMENT = datetime.timedelta(seconds=1)

  def __init__(self, initial_value=DEFAULT_NOW, increment=DEFAULT_INCREMENT):
    """Initializes a FakeNow object.

    Args:
      initial_value: First value to return (datetime.datetime)
      increment: Amount to increment each call (datetime.timedelta)
    """
    self.now = initial_value
    self.increment = increment

  def __call__(self):
    """Returns the current clock value.

    Returns:
      datetime.datetime

    Postconditions:
      Next call will return current value plus increment.
    """
    now = self.now
    self.now += self.increment
    return now
