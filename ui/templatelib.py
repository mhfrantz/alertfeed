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

__author__ = 'api.roman.public@gmail.com (Roman Nurik)'

import logging
import os

from google.appengine.ext import webapp
from google.appengine.api import users

register = webapp.template.create_template_register()

# Keys for each instance of this app.
JSAPI_KEYS = {
  'gongo-dev.appspot.com:80': 'ABQIAAAAsc0UQXoo2BnAJLhtpWCJFBS5gYxShnUObVA4VEJAsXhjFwcoxhRau7hEEpIuasKe44kdgfsOyEFcUQ',
  'localhost:8080': 'ABQIAAAAa-nOaft0HwDB8qjrdQrFuhTwM0brOpm-All5BF6PoaKBxRWWERRwoUXW--ZXndf0j4fjnyMTJW65GQ',
}

@register.simple_tag
def jsapi_key():
  # the os environ is actually the current web request's environ
  server_key = '%s:%s' % (os.environ['SERVER_NAME'], os.environ['SERVER_PORT'])
  logging.debug("server_key: %s", server_key)
  return JSAPI_KEYS[server_key] if server_key in JSAPI_KEYS else ''

def _default_dest_url():
  return os.environ['PATH_INFO'] + (('?' + os.environ['QUERY_STRING'])
                                    if os.environ['QUERY_STRING'] else '')

@register.simple_tag
def login_url(dest_url=''):
  dest_url = dest_url or _default_dest_url()
  return users.create_login_url(dest_url)

@register.simple_tag
def logout_url(dest_url=''):
  dest_url = dest_url or _default_dest_url()
  return users.create_logout_url(dest_url)

@register.simple_tag
def test_curpath():
  return str(os.environ)
