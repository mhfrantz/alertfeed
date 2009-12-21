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

ParseCapAlertNodes extracts a DOM containing CAP <alert> nodes from XML.

CapParser (abstract) can parse CAP (XML) to produce in-memory representations
of each <alert> element.

MemoryCapParser is a concrete subclass of CapParser that produces data model
objects defined in the third party caplib library.  This parsing code is more
permissive than the caplib parser, and accumulates parsing errors rather than
aborting the parse on the first error.  (The accumulated parsing errors are
eventually stored in the CapAlert and CrawlShard Datastore models.)

The code in this module must track the evolving CAP standard.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import traceback
from xml.dom import minidom

try:
  # Google3 environment.
  from google3.apphosting.runtime.apiproxy_errors import DeadlineExceededError
  from google3.pyglib import logging

  from google3.dotorg.gongo.appengine_cap2kml import cap_schema_mem
  from google3.dotorg.gongo.appengine_cap2kml import caplib_adapter
  from google3.dotorg.gongo.appengine_cap2kml import xml_util
except ImportError:
  import logging
  from google.appengine.runtime import DeadlineExceededError
  import cap_schema_mem
  import caplib_adapter
  import xml_util


class Error(Exception):
  pass


class RecoverableError(Error):
  """Base exception for parse errors that do not abort the parse."""


class NoInfoNodesError(RecoverableError):
  """Used when a CAP alert has no info nodes."""

  def __init__(self):
    RecoverableError.__init__(self, 'No alert.info nodes')


class NoAreaNodesError(RecoverableError):
  """Used when a CAP alert.info node has no area nodes."""

  def __init__(self):
    RecoverableError.__init__(self, 'No alert.info.area nodes')


class CapFormatError(Error):
  """Raised when a CAP document is not one of the supported formats."""

  def __init__(self, text, root_cause):
    """Initializes an CapFormatError object.

    Args:
      text: Text that was parsed (string)
      root_cause: Further explanation of the error (string)
    """
    Error.__init__(
        self, 'CAP format error: %s: %s' % (root_cause, text))


class NotCapError(CapFormatError):
  """Raised when a document does not appear to be CAP."""

  def __init__(self, text):
    """Initializes an NotCapError object.

    Args:
      text: Text that was parsed (string)
    """
    CapFormatError.__init__(self, text, 'Unrecognized document type')


def ParseCapAlertNodes(cap_text):
  """Extracts the CAP alert XML node from the CAP document.

  Args:
    cap_text: XML document containing CAP.

  Returns:
    List of zero or more DOM object(s) (xml.dom.Node) representing the CAP
    alert node(s).
  """
  doc = minidom.parseString(cap_text)
  # TODO(Matt Frantz): Deal with namespaces formally.
  for tag in ['alert', 'cap:alert']:
    alerts = doc.getElementsByTagName(tag)
    if alerts:
      return alerts
  return []


class CapParser(object):
  """Stateless parser for converting CAP Alert XML to data model objects.

  The abstract methods defined in this class are factory methods for producing
  the data model objects corresponding to each composite CAP element: <alert>,
  <info>, <resource>, and <area>.
  """

  def __init__(self, query=None):
    """Initializes a CapParser object.

    Args:
      query: web_query.Query object for applying deferred filtering.
    """
    self._query = query

  def MakeAlert(self, new_alert_model, alert_text):
    """Parses CAP XML data and produces data model object.

    The alert model objects returned may not represent conforming CAP alerts.
    This parser is more forgiving than the standard would require.  Any
    deviations are indicated in the list of errors that is returned.

    Args:
      new_alert_model: Factory that returns a CAP Alert model object.
      alert_text: XML representing the alert (unicode)

    Returns:
      (alert_model, errors)
      alert_model: The CAP model object returned by new_alert_model factory,
          populated.
      errors: List of recoverable parse errors, possibly empty.

    Raises:
      CapFormatError: Problem interpreting the alert_text as a CAP alert.
      DeadlineExceededError: Ran out of time.
   """
    try:
      alert_nodes = ParseCapAlertNodes(alert_text)
      # The CAP standard does not allows multiple <alert> nodes.
      if len(alert_nodes) == 1:
        alert_model = new_alert_model()
        errors = self._ParseAlert(alert_model, alert_nodes[0])
        return alert_model, errors
      elif len(alert_nodes) > 1:
        raise CapFormatError(alert_text, 'More than one <alert> node.')
      else:
        raise NotCapError(alert_text)
    except (CapFormatError, DeadlineExceededError, AssertionError):
      raise
    except Exception, e:
      logging.debug(traceback.format_exc())
      raise CapFormatError(alert_text, 'Parse error: %s' % e)

  # Maps of XML tag name to model attribute name, in case they differ.  By
  # default, the same name is assumed.
  ALERT_NAME_MAP = None
  INFO_NAME_MAP = None
  RESOURCE_NAME_MAP = None
  AREA_NAME_MAP = None

  def _NewCapInfo(self, alert_model):
    """Factory method for CAP Info model objects.

    Args:
      alert_model: CAP Alert model object, of the type returned by the
          new_alert_model factory provided to ParseCap.

    Returns:
      CAP Info model object.
    """
    raise NotImplementedError()

  def _NewCapResource(self, info_model):
    """Factory method for CAP Resource model objects.

    Args:
      info_model: CAP Info model object, of the type returned by _NewCapInfo.

    Returns:
      CAP Resource model object.
    """
    raise NotImplementedError()

  def _NewCapArea(self, info_model):
    """Factory method for CAP Area model objects.

    Args:
      info_model: CAP Info model object, of the type returned by _NewCapInfo.

    Returns:
      CAP Area model object.
    """
    raise NotImplementedError()

  def _MakeCapInfo(self, alert_model, info_node):
    """Creates a CAP Info model object, and populates it from XML node.

    Args:
      alert_model: CAP Alert model object.
      info_node: Alert.info node (xml.dom.Node)

    Returns:
      (info_model, errors)
      info_model: CAP Info model object, of the type returned by _NewCapInfo,
          already populated and stored.
      errors: List of recoverable errors encountered.
    """
    info_model = self._NewCapInfo(alert_model)
    errors = self._ParseCapInfo(info_model, info_node)
    return info_model, errors

  def _MakeCapResource(self, info_model, resource_node):
    """Creates a CAP Resource model object, and populates it from XML node.

    Args:
      info_model: CAP Info model object.
      resource_node: Alert.info.resource node (xml.dom.Node)

    Returns:
      (resource_model, errors)
      resource_model: CAP Resource model object, of the type returned by
          _NewCapResource, already populated and stored.
      errors: List of recoverable errors encountered.
    """
    resource_model = self._NewCapResource(info_model)
    errors = self._ParseCapResource(resource_model, resource_node)
    return resource_model, errors

  def _MakeCapArea(self, info_model, area_node):
    """Creates a CAP Area model object, and populates it from XML node.

    Args:
      info_model: CAP Info model object.
      area_node: Alert.info.area node (xml.dom.Node)

    Returns:
      (area_model, errors)
      area_model = CAP Area model object, of the type returned by _NewCapArea,
          already populated and stored.
      errors: List of recoverable errors encountered.
    """
    area_model = self._NewCapArea(info_model)
    errors = self._ParseCapArea(area_model, area_node)
    return area_model, errors

  def _ParseAlert(self, alert_model, alert_node):
    """Parses CAP alert node and populates data model.

    Args:
      alert_model: CAP Alert model object, modified in place.
      alert_node: Alert node (xml.dom.Node)

    Returns:
      List of recoverable errors, possibly empty.
    """
    errors = []
    errors.extend(xml_util.CopyStringNodes(alert_model, alert_node, [
        'identifier', 'sender', 'status', 'msgType', 'source', 'scope',
        'restriction'], name_map=self.ALERT_NAME_MAP))
    errors.extend(xml_util.CopyStringNodeLists(alert_model, alert_node, [
        'code', 'references'], name_map=self.ALERT_NAME_MAP))
    errors.extend(xml_util.CopyTextNodes(alert_model, alert_node, [
        'addresses', 'note', 'incidents'], name_map=self.ALERT_NAME_MAP))
    errors.extend(xml_util.CopyDateTimeNodes(alert_model, alert_node, ['sent'],
                                             name_map=self.ALERT_NAME_MAP))
    info_nodes = alert_node.getElementsByTagName('info')
    if info_nodes:
      for info_node in info_nodes:
        unused_info_model, info_errors = self._MakeCapInfo(
            alert_model, info_node)
        errors.extend(info_errors)
    else:
      errors.append(NoInfoNodesError())

    return errors

  def _ParseCapInfo(self, info_model, info_node):
    """Parses alert.info data and populates the data model.

    Args:
      info_model: CAP Info model object, modified in place.
      info_node: Alert.info node (xml.dom.Node)

    Returns:
      List of recoverable errors, possibly empty.
    """
    errors = []
    errors.extend(xml_util.CopyStringNodes(
        info_model, info_node, [
        'language', 'urgency', 'severity', 'certainty', 'audience',
        'senderName', 'web', 'contact'],
        name_map=self.INFO_NAME_MAP))
    errors.extend(xml_util.CopyStringNodeLists(
        info_model, info_node, ['category', 'responseType'],
        name_map=self.INFO_NAME_MAP))
    errors.extend(xml_util.CopyTextNodes(
        info_model, info_node, [
        'event', 'headline', 'description', 'instruction'],
        name_map=self.INFO_NAME_MAP))
    errors.extend(xml_util.CopyDateTimeNodes(
        info_model, info_node, ['effective', 'onset', 'expires'],
        name_map=self.INFO_NAME_MAP))
    for resource_node in info_node.getElementsByTagName('resource'):
      unused_resource_model, resource_errors = self._MakeCapResource(
          info_model, resource_node)
      errors.extend(resource_errors)
    area_nodes = info_node.getElementsByTagName('area')
    if area_nodes:
      for area_node in area_nodes:
        unused_area_model, area_errors = self._MakeCapArea(
            info_model, area_node)
        errors.extend(area_errors)
    else:
      errors.append(NoAreaNodesError())

    return errors

  def _ParseCapResource(self, resource_model, resource_node):
    """Parses alert.info.resource data and populates the data model.

    Args:
      resource_model: CAP Resource model object, modified in place.
      resource_node: Alert.info.resource node (xml.dom.Node)

    Returns:
      List of recoverable errors, possibly empty.
    """
    errors = []
    errors.extend(xml_util.CopyStringNodes(
        resource_model, resource_node, ['resourceDesc', 'mimeType', 'uri'],
        name_map=self.RESOURCE_NAME_MAP))
    errors.extend(xml_util.CopyTextNodes(
        resource_model, resource_node, ['derefUri', 'digest'],
        name_map=self.RESOURCE_NAME_MAP))
    errors.extend(xml_util.CopyIntegerNodes(
        resource_model, resource_node, ['size'],
        name_map=self.RESOURCE_NAME_MAP))
    return errors

  def _ParseCapArea(self, area_model, area_node):
    """Parses alert.info.area data and populates the data model.

    Args:
      area_model: CAP Area model object, modified in place.
      area_node: Alert.info.area node (xml.dom.Node)

    Returns:
      List of recoverable errors, possibly empty.
    """
    errors = []
    errors.extend(xml_util.CopyTextNodes(
        area_model, area_node, ['areaDesc', 'altitude', 'ceiling'],
        name_map=self.AREA_NAME_MAP))
    # Parse 'polygon', 'circle' lists.
    errors.extend(xml_util.CopyTextNodeLists(
        area_model, area_node, ['polygon'], name_map=self.AREA_NAME_MAP))
    errors.extend(xml_util.CopyStringNodeLists(
        area_model, area_node, ['circle'], name_map=self.AREA_NAME_MAP))
    # TODO(Matt Frantz): Parse geocode tag/value pairs.
    return errors


class MemoryCapParser(CapParser):
  """Stateless parser that generates in-memory models from cap_schema_mem."""

  ALERT_NAME_MAP = caplib_adapter.ALERT_NAME_MAP
  INFO_NAME_MAP = caplib_adapter.INFO_NAME_MAP
  RESOURCE_NAME_MAP = caplib_adapter.RESOURCE_NAME_MAP
  AREA_NAME_MAP = caplib_adapter.AREA_NAME_MAP

  def _NewCapInfo(self, alert_model):
    """Factory method for CAP Info model objects.

    Args:
      alert_model: cap_schema_mem.ShadowAlert object

    Returns:
      New cap_schema_mem.ShadowInfo object which has been added to
      alert_model.info.
    """
    info = cap_schema_mem.ShadowInfo(query=self._query)
    alert_model.info.append(info)
    return info

  def _NewCapResource(self, info_model):
    """Factory method for CAP Resource model objects.

    Args:
      info_model: cap_schema_mem.ShadowInfo object

    Returns:
      New cap_schema_mem.ShadowResource object which has been added to
      info_model.resource.
    """
    resource = cap_schema_mem.ShadowResource()
    info_model.resource.append(resource)
    return resource

  def _NewCapArea(self, info_model):
    """Factory method for CAP Area model objects.

    Args:
      info_model: cap_schema_mem.ShadowInfo object

    Returns:
      New cap_schema_mem.ShadowArea object which has been added to
      info_model.area.
    """
    area = cap_schema_mem.ShadowArea()
    info_model.area.append(area)
    return area
