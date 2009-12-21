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

"""Gongo frontend/view handlers."""

__author__ = 'api.roman.public@gmail.com (Roman Nurik)'

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

import webapp_util


template.register_template_library(
    'django.contrib.humanize.templatetags.humanize')
template.register_template_library('ui/templatelib')


class Error(Exception):
  pass


class FrontView(webapp.RequestHandler):
  """Responds to requests from cron to advance the crawl."""

  def get(self):
    # We're done!
    webapp_util.WriteTemplate(self.response, 'ui/templates/front.html', {})


application = webapp.WSGIApplication(
    [('/', FrontView),
     ],
    debug=True)


def main():
  run_wsgi_app(application)


if __name__ == '__main__':
  main()
