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

"""Implements a paged Datastore query via CGI and Django templates.

The PagedQuery class assists the CGI handler, and the pager.html implements a
simple control element.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'


class PagedQuery(object):
  """Handler of a page containing a paged query."""

  def __init__(self, default_limit=20):
    """Initializes a PagedQuery object.

    Args:
      default_limit: If request does not specify the limit, this default will
          be used (int)
    """
    self.__default_limit = default_limit
    self.__offset = 0
    self.__limit = default_limit

  def ParseRequest(self, request):
    """Parses offset/limit from the CGI request.

    Args:
      request: webapp.Request object

    Returns:
      offset (int), limit (int)
    """
    offset = request.get('offset')
    if offset:
      try:
        offset = int(offset)
      except ValueError:
        offset = 0
      if offset < 0:
        offset = 0
    else:
      offset = 0

    limit = request.get('limit')
    if limit:
      try:
        limit = int(limit)
      except ValueError:
        limit = default_limit
      if limit <= 0:
        limit = DEFAULT_LIMIT
    else:
      limit = 20
    self.__offset, self.__limit = offset, limit
    return offset, limit

  def MakeTemplateParams(self, base_url, params=None):
    """Returns the Django template parameters that control a paged query.

    These parameters are designed for pager.html or a compatible template.

    Args:
      base_url: URL of the paged query (str)
      params: Dict of additional CGI parameters (str:str)

    Returns:
      Dict with Django template parameters.
    """
    if params:
      param_str = '&'.join(['%s=%s' % (key, value)
                            for key, value in params.iteritems()])
    else:
      param_str = ''

    return dict(
        base_url=base_url, pager_params=param_str,
        limit=self.__limit, offset=self.__offset,
        prev=max(0, self.__offset - self.__limit),
        next=self.__offset + self.__limit)
