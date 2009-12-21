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

"""CAP parsing utilities.

ParseCapIndex can parse either RSS or ATOM feed indices of CAP files.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

from xml.dom import minidom

try:
  # Google3 environment.
  from google3.apphosting.runtime.apiproxy_errors import DeadlineExceededError
  from google3.dotorg.gongo.appengine_cap2kml import xml_util
except ImportError:
  from google.appengine.runtime import DeadlineExceededError
  import xml_util


class Error(Exception):
  pass


class CapIndexFormatError(Error):
  """Raised when a CAP index document is not one of the supported formats."""

  def __init__(self, text, root_cause):
    """Initializes an CapIndexFormatError object.

    Args:
      text: Text that was parsed (string)
      root_cause: Further explanation of the error (string)
    """
    Error.__init__(
        self, 'CAP index format error: %s: %s' % (root_cause, text))


def ParseCapIndex(index_text):
  """Parses a CAP index and returns references to CAP files.

  Args:
    index_text: XML (RSS or ATOM) with links to CAP files (string)

  Returns:
    List of CAP URL's (strings)

  Raises:
    CapIndexFormatError, if there is a problem parsing.
  """
  try:
    # Must be XML.
    doc = minidom.parseString(index_text)

    # See if it is RSS.
    rss_nodes = doc.getElementsByTagName('rss')
    if rss_nodes:
      # Shouldn't have more than one, but it's easy enough to support.
      urls = []
      for rss_node in rss_nodes:
        urls.extend(_ParseCapIndexRss(rss_node))
      return urls

    # See if it is ATOM.
    feed_nodes = doc.getElementsByTagName('feed')
    if not feed_nodes:
      # TODO(Matt Frantz): Really support XML namespaces.
      feed_nodes = doc.getElementsByTagName('atom:feed')

    if feed_nodes:
      # Shouldn't have more than one, but it's easy enough to support.
      urls = []
      for feed_node in feed_nodes:
        urls.extend(_ParseCapIndexAtom(feed_node))
      return urls

    # Not sure what it is.
    raise CapIndexFormatError(index_text, 'Unrecognized document type')
  except (CapIndexFormatError, DeadlineExceededError, AssertionError):
    raise
  except Exception, e:
    raise CapIndexFormatError(index_text, 'Parse error: %s' % e)


def _ParseCapIndexRss(rss):
  """Parses a CAP index in the RSS format.

  Args:
    rss: RSS CAP index document (xml.dom.Node object)

  Returns:
    List of CAP URL's (strings)
  """
  link_urls = []
  for item in rss.getElementsByTagName('item'):
    link_node_name = 'link';
    link_nodes = item.getElementsByTagName(link_node_name)

    for link_node in link_nodes:
      link_url = xml_util.GetText(link_nodes[0].childNodes)
      if link_url:
        link_urls.append(link_url)

  return link_urls


def _ParseCapIndexAtom(atom):
  """Parses a CAP index in the ATOM format.

  Args:
    atom: ATOM CAP index document (xml.dom.Node object)

  Returns:
    List of CAP URL's (strings)
  """
  link_urls = []
  entries = atom.getElementsByTagName('entry')
  if not entries:
    # TODO(Matt Frantz): Really support XML namespaces.
    entries = atom.getElementsByTagName('atom:entry')

  for entry in entries:
    link_nodes = entry.getElementsByTagName('link')
    if not link_nodes:
      # TODO(Matt Frantz): Really support XML namespaces.
      link_nodes = entry.getElementsByTagName('atom:link')

    for link_node in link_nodes:
      # TODO(Matt Frantz): What about other kinds of links? http://b/2188342
      href = link_nodes[0].getAttribute('href')
      if href:
        link_urls.append(href)

  return link_urls
