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

"""Query interface to the Datastore populated by cap_mirror."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import logging
import traceback
from xml.parsers import expat

# Third party imports.
import pyfo
import cap as caplib

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.runtime import DeadlineExceededError

import cap2kml
import cap_parse_mem
import cap_schema
import cap_schema_mem
import web_query
import webapp_util
import xml_util


CAP_V1_1_XMLNS_URN = 'urn:oasis:names:tc:emergency:cap:1.1'


def _MakeCapSchema():
  # TODO(Matt Frantz): Permit different set of operators for timestamps, geo.
  scalar_ops = web_query.Operators.SCALAR_ALL
  datetime_ops = web_query.Operators.DATETIME_ALL
  key_ops = web_query.Operators.KEY_ALL
  list_ops = web_query.Operators.LIST_ALL
  default_model = 'CapAlert'
  return web_query.Schema({
      'Feed': {
          'url': scalar_ops},
      default_model: {
          'crawl': key_ops,
          'feed': key_ops,
          'url': scalar_ops,
          'identifier': scalar_ops,
          'sender': scalar_ops,
          'sent': datetime_ops,
          'status': scalar_ops,
          'msgType': scalar_ops,
          'source': scalar_ops,
          'scope': scalar_ops,
          'restriction': scalar_ops,
          'code': list_ops,
          'references': list_ops,
          # Info
          'language': list_ops,
          'category': list_ops,
          'responseType': list_ops,
          'urgency': list_ops,
          'severity': list_ops,
          'certainty': list_ops,
          'audience': list_ops,
          'effective': datetime_ops,
          'onset': datetime_ops,
          'expires': datetime_ops,
          'senderName': list_ops,
          'web': list_ops,
          'contact': list_ops,
          # Resource
          'resourceDesc': list_ops,
          'mimeType': list_ops,
          'size': list_ops,
          'uri': list_ops,
          # Area
          'altitude': list_ops,
          'ceiling': list_ops,
          },
      }, default_model)


CAP_SCHEMA = _MakeCapSchema()


class CapQueryResult(object):
  """Contains a single element of a CapQuery result.

  Attributes:
    model: cap_schema_mem.ShadowAlert object
    text: Original XML text (str or unicode)
    url: URL from which the text was fetched (str or unicode)
  """

  def __init__(self, model, text, url):
    self.model = model
    self.text = text
    self.url = url


class CapQuery(webapp.RequestHandler):
  """Handler for requests that require queries of Datastore.

  This class includes the query execution planning logic.

  Queries involve either a direct query on the main CAP model (CapAlert), or
  an indirect query via references from Feed.  The _WriteResponse virtual
  method will be provided with an iterable of instances of CAP Alert model
  types.
  """

  def get(self):
    """Parses query predicates and responds with error screens or CAP data."""
    user_query, unknown_arguments = CAP_SCHEMA.QueryFromRequest(self.request)
    unknown_arguments = self._HandleUnknownArguments(
        frozenset(unknown_arguments))
    if unknown_arguments:
      webapp_util.WriteTemplate(self.response, 'unknown_arguments.html',
                                {'unknown_arguments': unknown_arguments,
                                 'models': CAP_SCHEMA.Help()})
      return

    # Choose the query executor.
    # TODO(Matt Frantz): Better query execution planning.

    if 'Feed' in user_query.models:
      execute = self._QueryByFeed
    elif 'CapAlert' in user_query.models:
      execute = self._QueryByCapAlert
    else:
      webapp_util.WriteTemplate(self.response, 'no_arguments.html',
                                dict(models=CAP_SCHEMA.Help()))
      return

    # Use the most recent completed crawl for each feed to serve queries.
    restricted_query = self._ApplyLastCrawlsToQuery(user_query)

    # Execute the query.
    alerts = execute(user_query, restricted_query)

    # If an error response is written, no CAP data will be returned.
    if alerts is not None:
      self._WriteResponse(alerts, user_query)

  def _HandleUnknownArguments(self, unknown_arguments):
    """Filters arguments that are not web_query parameters.

    Args:
      unknown_arguments: Set (possibly empty) of CGI argument names (frozenset
          of str or unicode).

    Returns:
      Set of truly unknown arguments for generating an error screen (frozenset
          of str or unicode).
    """
    raise NotImplementedError()

  def _WriteResponse(self, alerts, user_query):
    """Abstract method that writes the response of a slow path query.

    Args:
      alerts: Iterable of CapQueryResult objects.
      user_query: What the user specified (web_query.Query)

    Postconditions:
      self.response is populated.
    """
    raise NotImplementedError()

  def _ApplyLastCrawlsToQuery(self, user_query):
    """Restrict the user query to the latest crawl.

    Args:
      user_query: web_query.Query object

    Returns:
      web_query.Query object with crawl predicates
    """
    crawls = cap_schema.LastCrawls()
    if not crawls:
      return user_query

    # Extend the list of predicates with Crawl predicates.
    predicates = list(user_query.predicates)
    predicates.append(
        web_query.SimpleComparisonPredicate('CapAlert', 'crawl', list(crawls),
                                            web_query.Operators.KEY_IN))
    return web_query.Query(predicates)

  def _QueryByFeed(self, user_query, restricted_query):
    """Queries by following the Feed -> Cap hierarchy.

    Args:
      user_query: What the user specified (web_query.Query)
      restricted_query: Last crawled version of user_query (web_query.Query)

    Returns:
      Iterable of CapQueryResult objects.
    """
    # Lookup the feeds.
    gql_list, gql_params = restricted_query.ApplyToGql('Feed')
    feed_query = db.GqlQuery(
        'SELECT __key__ FROM Feed WHERE %s' % ' AND '.join(gql_list),
        **gql_params)
    feed_keys = list(feed_query)
    if not feed_keys:
      # Show all valid feed URL's in the error page.
      all_feed_query = cap_schema.Feed.all()
      webapp_util.WriteTemplate(
          self.response, 'unknown_feed_url.html',
          {'unknown_feed_url': repr(self.request.get('Feed.url')),
           'feed_urls': [repr(x.url) for x in all_feed_query]})
      return None

    # Extend the list of predicates with Feed.key predicates.
    predicates = list(restricted_query.predicates) + [
        web_query.SimpleComparisonPredicate('CapAlert', 'feed', feed_keys,
                                            web_query.Operators.KEY_IN)]
    cap_query = web_query.Query(predicates)
    return self._DoCapAlertQuery(user_query, cap_query)

  def _QueryByCapAlert(self, user_query, restricted_query):
    """Queries the CapAlert models directly.

    Args:
      user_query: What the user specified (web_query.Query)
      restricted_query: Last crawled version of user_query (web_query.Query)

    Returns:
      Iterable of CapQueryResult objects.
    """
    assert 'Feed' not in user_query.models
    return self._DoCapAlertQuery(user_query, restricted_query)

  def _DoCapAlertQuery(self, user_query, restricted_query):
    """Executes a CapAlert query and returns the CAP representations.

    Args:
      user_query: What the user specified (web_query.Query)
      restricted_query: Last crawled version of user_query (web_query.Query)

    Returns:
      Iterable of CapQueryResult objects.
    """
    return self._DoQuery('CapAlert', cap_schema.CapAlert,
                         user_query, restricted_query)

  def _DoQuery(self, model_name, model_class, user_query, restricted_query):
    """Runs the Datastore query.

    Args:
      model_name: Model name (str)
      model_class: db.Model subclass
      user_query: What the user specified (web_query.Query)
      restricted_query: Last crawled version of user_query (web_query.Query)

    Returns:
      Iterable of CapQueryResult objects.
    """
    gql_list, gql_params = restricted_query.ApplyToGql(model_name)
    db_query = model_class.gql('WHERE %s' % ' AND '.join(gql_list),
                               **gql_params)
    model_count = 0

    # Avoid duplicate alerts.
    alert_texts = set()

    # We may need the cap_parse parser.
    parser = cap_parse_mem.MemoryCapParser(query=user_query)

    # Count how many alerts were handled in different execution paths.
    caplib_alerts = 0
    parseable_alerts = 0
    clean_alerts = 0
    unparseable_alerts = 0
    unicode_alerts = 0
    bad_xml_alerts = 0

    # Transform ShadowCap list into a list of CapQueryResult objects.
    alerts = []
    for model in db_query:
      model_count += 1

      # Suppress duplicates.
      alert_text = model.text
      if alert_text in alert_texts:
        continue
      else:
        alert_texts.add(alert_text)

      # We will eventually have to get a Cap, ShadowCap, or proxy object.
      # We'll get it in the most efficient way possible.

      # Try it with the standard-conforming parser.
      alert_model = CapQuery._ParseConformingCap(alert_text, query=user_query)
      if alert_model:
        caplib_alerts += 1
      else:
        # If we were unable to use the caplib parser, try our own.
        alert_model, errors = CapQuery._ParseNonconformingCap(parser, alert_text)
        if alert_model:
          if errors:
            parseable_alerts += 1
          else:
            clean_alerts += 1
        else:
          unparseable_alerts += 1

      # Filter any predicates that might not have been applied in the GQL query.
      if alert_model and user_query.PermitsModel('Cap', alert_model):
        # Save the model and the original XML.
        alerts.append(
            CapQueryResult(alert_model, alert_text, model.url))

    unique_model_count = len(alerts)
    logging.info(
        ('Visited %(model_count)d models, %(unique_model_count)d unique = ' +
         '%(caplib_alerts)d caplib + %(clean_alerts)d clean + ' +
         '%(parseable_alerts)d parseable + %(unparseable_alerts)d unparseable'),
        locals())
    return alerts

  @classmethod
  def _ParseConformingCap(cls, alert_text, query=None):
    """Parses CAP alert with the standard-conforming caplib parser.

    Args:
      alert_text: XML representation of the alert (unicode)
      query: web_query.Query object for deferred filtering.

    Returns:
      cap_schema_mem.ShadowCap object or None if there was a problem parsing.
    """
    cap_namespaces = [CAP_V1_1_XMLNS_URN]
    try:
      # Convert to string, since expat parser does not seem to support
      # Unicode.
      # TODO(Matt Frantz): Figure out why we have to do this.  Expat claims
      # to support Unicode.  Maybe we can use a different parser for
      # caplib.
      alert_text_str = str(alert_text)
      for cap_namespace in cap_namespaces:
        try:
          # Parse the XML into a caplib.Alert object.
          alert_model = caplib.ParseString(alert_text_str,
                                           namespace=cap_namespace)
          # Create a shadow alert object that can apply the deferred query.
          shadow_alert = cap_schema_mem.ShadowAlert(query=query)
          # Copy the data from the original alert to the shadow using an
          # internal method (defined in caplib's Container class).  The
          # Container constructor is overly restrictive about the type of the
          # template argument, so this hack is necessary.
          # TODO(Matt Frantz): Avoid this hack.
          shadow_alert._init_from_obj_(alert_model)
          break
        except (caplib.ConformanceError, ValueError, TypeError), e:
          logging.debug('caplib error %s (%s) parsing %r',
                        type(e), e, alert_text_str)

    except UnicodeEncodeError, e:
      # We can't convert to string, so we can't really parse this with the
      # caplib parser.
      logging.debug('UnicodeEncodeError (%s) parsing %r', e, alert_text)
    except expat.ExpatError, e:
      # XML parsing errors are namespace-independent (right?), so log it
      # and stop trying.
      logging.debug('ExpatError (%s) parsing %r', e, alert_text)

    return None

  @classmethod
  def _ParseNonconformingCap(cls, parser, alert_text, query=None):
    """Parses CAP alert with our own permissive parser.

    Args:
      parser: cap_parse_mem.MemoryCapParser object
      alert_text: XML representation of the alert (unicode)
      query: web_query.Query object for deferred filtering.

    Returns:
      (alert_model, errors)
      alert_model: cap_schema_mem.ShadowCap object, or None if there was an
          unrecoverable error.
      errors: List of recoverable errors, if any.
    """
    try:
      new_alert_model = lambda: cap_schema_mem.ShadowAlert(query=query)
      return parser.MakeAlert(new_alert_model, alert_text)
    except cap_parse_mem.Error, e:
      logging.debug('%s', traceback.format_exc())
      logging.debug('cap_parse_mem error %s (%s) parsing %r',
                    type(e), e, alert_text)

    return None, []

  @classmethod
  def _NormalizeAlertText(cls, alert_text):
    """Normalizes the XML text representation of a CAP alert node.

    Strips any tag namespace prefixes.

    Args:
      alert_text: XML representation (str or unicode)

    Returns:
      Normalized XML representation (unicode)
    """
    alert_nodes = cap_parse_mem.ParseCapAlertNodes(alert_text)
    if len(alert_nodes) > 1:
      logging.error(
          'How did that get in there?  I thought cap_mirror rejected CAPs' +
          ' with more than one alert node!\n%r', alert_text)
    alert_node = alert_nodes[0]
    cls._NormalizeAlert(alert_node, CAP_V1_1_XMLNS_URN)
    return xml_util.NodeToString(alert_node)

  @classmethod
  def _NormalizeAlert(cls, node, namespace_urn):
    """Normalizes the XML representation of a CAP alert node.

    Strips any tag namespace prefixes.

    Args:
      node: xml.dom.Node representing the CAP alert (modified in place)
      namespace_urn: XML namespace URN (str)
    """
    # Apply the namespace prefix throughout.
    cls._NormalizeNode(node)
    # Strip out any xmlns attributes.
    attributes = node.attributes
    for i in xrange(attributes.length):
      attribute = attributes.item(i)
      name = attribute.name
      if name == 'xmlns' or name.startswith('xmlns:'):
        node.removeAttribute(name)
    # Apply the XML namespace attribute to the alert node.
    node.setAttribute('xmlns', namespace_urn)

  @classmethod
  def _NormalizeNode(cls, node):
    """Normalizes the XML representation of an XML node.

    Strips any tag namespace prefix.

    Args:
      node: xml.dom.Node (modified in place).
    """
    try:
      tag = node.tagName
    except AttributeError:
      # Not an XML element.
      return

    node.tagName = cls._NormalizeTag(tag)
    for child in node.childNodes:
      cls._NormalizeNode(child)

  @classmethod
  def _NormalizeTag(cls, tag):
    """Normalizes the XML tag name.

    Strips any tag namespace prefix.

    Args:
      tag: XML node tag (str)

    Returns:
      tag without any namespace prefix.
    """
    colon = tag.find(':')
    if colon >= 0:
      tag = tag[colon + 1:]
    return tag


class Cap2Kml(CapQuery):
  """Handler for cap2kml requests that produce KML responses.

  Attributes:
    as_xml: If True, response content type will be XML.  If False, it will be
        KML.  (Written by _HandleUnknownArguments; read by _WriteResponse.)
  """

  def _HandleUnknownArguments(self, unknown_arguments):
    """Filters arguments that are not web_query parameters.

    Args:
      unknown_arguments: Set (possibly empty) of CGI argument names (frozenset
          of str or unicode).

    Returns:
      Set of truly unknown arguments for generating an error screen (frozenset
          of str or unicode).
    """
    unknown_arguments = set(unknown_arguments)
    # Support alternate response content type.
    self.as_xml = 'as_xml' in unknown_arguments and self.request.get('as_xml')
    unknown_arguments.discard('as_xml')
    return frozenset(unknown_arguments)

  def _WriteResponse(self, alerts, user_query):
    """Writes a KML response.

    Args:
      alerts: Iterable of CapQueryResult objects.
      user_query: What the user specified (web_query.Query)

    Postconditions:
      self.response is populated.
    """
    logging.info('Generating KML')
    placemarks = []
    for alert in alerts:
      try:
        placemark = cap2kml.CapAlertAsKmlPlacemark(alert.model).ToKml()
        placemarks.append(placemark)
      except (DeadlineExceededError, AssertionError):
        raise
      except Exception, e:
        logging.exception(e)

    if self.as_xml:
      content_type = 'text/xml'
    else:
      content_type = 'application/vnd.google-earth.kml+xml'

    logging.info('Writing response as %s', content_type)
    self.response.headers['Content-Type'] = content_type
    self.response.out.write(pyfo.pyfo(cap2kml.Kml(placemarks), prolog=True))


class Cap2Atom(CapQuery):
  """Handler for cap2atom requests that produce ATOM responses."""

  def _HandleUnknownArguments(self, unknown_arguments):
    """Filters arguments that are not web_query parameters.

    Args:
      unknown_arguments: Set (possibly empty) of CGI argument names (frozenset
          of str or unicode).

    Returns:
      Set of truly unknown arguments for generating an error screen (frozenset
          of str or unicode).
    """
    # We don't have any additional arguments.
    return unknown_arguments

  def _WriteResponse(self, alerts, user_query):
    """Writes an ATOM index of CAP's.

    Args:
      alerts: Iterable of CapQueryResult objects.
      user_query: What the user specified (web_query.Query)

    Postconditions:
      self.response is populated.
    """
    # Generate a feed title based on the query.
    title = 'CapQuery: %s' % user_query

    # Normalize the XML.
    logging.info('Normalizing XML')
    # TODO(Matt Frantz): Some deferred predicates will be ignored because we are
    # returning to the source XML rather than allowing the shadow models to
    # apply the predicates.  When cap_parse is a complete parser, we can use
    # the model to generate the filtered, normalized XML.
    # TODO(Matt Frantz): We could normalize XML during crawl, although that
    # would make it difficult to apply improvements to the parser
    # retroactively on historical data.
    for alert in alerts:
      alert.text = Cap2Atom._NormalizeAlertText(alert.text)

    logging.info('Writing response')
    webapp_util.WriteTemplate(self.response, 'atom_index.xml',
                              dict(title=title, alerts=alerts))
    self.response.headers['Content-Type'] = 'text/xml'


class Cap2Dump(CapQuery):
  """Handler for cap2dump requests that produce debug XML responses."""

  def _HandleUnknownArguments(self, unknown_arguments):
    """Filters arguments that are not web_query parameters.

    Args:
      unknown_arguments: Set (possibly empty) of CGI argument names (frozenset
          of str or unicode).

    Returns:
      Set of truly unknown arguments for generating an error screen (frozenset
          of str or unicode).
    """
    # We don't have any additional arguments.
    return unknown_arguments

  def _WriteResponse(self, alerts, user_query):
    """Writes escaped XML rendering of CAP's.

    Args:
      alerts: Iterable of CapQueryResult objects.
      user_query: What the user specified (web_query.Query)

    Postconditions:
      self.response is populated.
    """
    # Generate a feed title based on the query.
    title = 'CapQuery: %s' % user_query

    logging.info('Writing response')
    self.response.headers['Content-Type'] = 'text/xml'
    webapp_util.WriteTemplate(self.response, 'cap_dump.xml',
                              dict(title=title, alerts=alerts))


application = webapp.WSGIApplication(
    [('/cap2kml', Cap2Kml),
     ('/cap2atom', Cap2Atom),
     ('/cap2dump', Cap2Dump),
     ],
    debug=True)


def main():
  run_wsgi_app(application)


if __name__ == '__main__':
  main()
