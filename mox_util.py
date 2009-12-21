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

"""Utilities for testing with Mox."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import google3
import mox


class AsStrContains(mox.StrContains):
  """Comparator to test whether an object's string form contains a string."""

  def __init__(self, search_string):
    mox.StrContains.__init__(self, search_string)

  def equals(self, rhs):
    return mox.StrContains.equals(self, str(rhs))
