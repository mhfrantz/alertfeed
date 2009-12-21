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

"""Utilities for dealing with the webapp framework."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import os

try:
  from google.appengine.api import users
  from google.appengine.ext.webapp import template

except ImportError:
  # google3
  from google3.apphosting.api import users
  from google3.apphosting.ext.webapp import template


def WriteTemplate(response, template_file, params):
  """Writes a response from a Django template.

  Args:
    response: webapp.Response object
    template_file: Path of a Django template, relative to this file (string)
    params: Dict of parameter name (string) to value (object)
  """
  path = os.path.join(os.path.dirname(__file__), template_file)
  params.update({'current_user': users.get_current_user()})
  html = template.render(path, params)
  response.out.write(html)
