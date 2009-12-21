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

"""XML utilities.

Useful for dealing with XML DOM objects (xml.dom.Node, etc.) in the context of
App Engine Datastore (google.appengine.ext.db).
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import re

try:
  import google3
  from google3.apphosting.ext import db
  from google3.apphosting.runtime.apiproxy_errors import DeadlineExceededError
  from google3.pyglib import logging

except ImportError, e:
  import logging
  from google.appengine.ext import db
  from google.appengine.runtime import DeadlineExceededError

import iso8601


# Allow independent control of the logging from this module.
try:
  logger = logging.getLogger(__file__)
  logger.setLevel(logging.INFO)
except AttributeError:
  logger = logging
  logger.warn('No independent logging')


class Error(Exception):
  pass


class RecoverableError(Error):
  """Base exception for CodeNode errors that do not abort the copy."""


class MultipleNodeError(RecoverableError):
  """Used by CopyNodes to indicate multiple XML nodes.

  Attributes:
    tag_name: Name of the XML node (str)
    child_nodes: List of two or more XML nodes (List of xml.dom.Node)
  """

  def __init__(self, tag_name, child_nodes):
    """Initializes a MultipleNodeError.

    Args:
      node_name: Name of the XML node (str)
      child_nodes: List of two or more XML nodes (List of xml.dom.Node)
    """
    RecoverableError.__init__(
        self, 'Duplicate child nodes "%s": %s' %
        (tag_name, ','.join([str(x) for x in child_nodes])))
    self.tag_name = tag_name
    self.child_nodes = child_nodes


class CopyNodeError(RecoverableError):
  """Used by CopyNodes to indicate an attribute that could not be copied.

  Attributes:
    attribute_name: Name of the target attribute (str)
    attribute_value: Text form of the value that provoked the error (str)
    root_cause: Exception that describes the error in detail (Exception)
  """

  def __init__(self, attribute_name, attribute_value, root_cause):
    """Initializes a CopyNodeError.

    Args:
      attribute_name: Name of the target attribute (str)
      attribute_value: Text form of the value that provoked the error (str)
      root_cause: Exception that describes the error in detail (Exception)
    """
    RecoverableError.__init__(
        self, 'Error copying %r from %r: %s: %s' %
        (attribute_name, attribute_value, root_cause.__class__.__name__,
         root_cause))
    self.attribute_name = attribute_name
    self.attribute_value = attribute_value
    self.root_cause = root_cause


def NodeToString(xml_node):
  """Returns an XML string.

  Args:
    xml_node: xml.dom.Node object

  Returns:
    String containing XML
  """
  return xml_node.toxml()


def GetText(nodes):
  """Concatenates text from text nodes.

  Args:
    nodes: List of xml.dom.Node objects

  Returns:
    Concatenation of text from any TEXT_NODE nodes (string)
  """
  text = ""
  for node in nodes:
    if node.nodeType == node.TEXT_NODE:
      text = text + node.data
  return text.strip()


def CopyNodes(model, node, names, converter, name_map=None):
  """Copies XML nodes into model attributes of the same respective names.

  Args:
    model: db.Model object
    node: xml.dom.Node object
    names: List of child node / model attribute names (strings)
    converter: Function which converts the text from the XML into an
        appropriate object for the data model.
    name_map: Dict to translate child node names to model attribute names
        (str:str)

  Returns:
    List of RecoverableError objects, possibly empty, representing multiple
    nodes that are found for any of the names, or if there is a problem
    converting the text into the appropriate value object.
  """
  errors = []
  for tag_name in names:
    child_nodes = node.getElementsByTagName(tag_name)
    if child_nodes:
      # If we have a validating XML parser, we shouldn't have to check this.
      if len(child_nodes) > 1:
        errors.append(MultipleNodeError(tag_name, child_nodes))
        continue

      text = GetText(child_nodes[0].childNodes)
      if text:
        if name_map and tag_name in name_map:
          attr_name = name_map[tag_name]
        else:
          attr_name = tag_name

        logger.debug('Setting "%s" to "%s"', attr_name, text)
        try:
          setattr(model, attr_name, converter(text))
        except (DeadlineExceededError, AssertionError):
          raise
        except Exception, e:
          errors.append(CopyNodeError(attr_name, text, e))

  return errors


def CopyNodeLists(model, node, names, converter, name_map=None):
  """Copies multiple XML nodes into model list attributes.

  Args:
    model: db.Model object
    node: xml.dom.Node object
    names: List of child node / model attribute names (strings)
    converter: Function which converts the text from the XML into an
        appropriate object for the data model.
    name_map: Dict to translate child node names to model attribute names
        (str:str)

  Returns:
    List of RecoverableError objects, possibly empty, representing problems
    converting the text into the appropriate value object.
  """
  errors = []
  for tag_name in names:
    for child_node in node.getElementsByTagName(tag_name):
      text = GetText(child_node.childNodes)
      if text:
        if name_map and tag_name in name_map:
          attr_name = name_map[tag_name]
        else:
          attr_name = tag_name

        logger.debug('Appending "%s" with "%s"', attr_name, text)
        try:
          getattr(model, attr_name).append(converter(text))
        except (DeadlineExceededError, AssertionError):
          raise
        except Exception, e:
          errors.append(CopyNodeError(attr_name, text, e))

  return errors


# Default Unicode encoding when strings are parsed.
# TODO(Matt Frantz): Decide if this is the right encoding.
_DEFAULT_ENCODING = 'utf8'


def ParseString(xml_text):
  """Converts XML text into a unicode object for a db.StringProperty attribute.

  The default encoding for the db module is 'ascii', but we may receive other
  encodings from XML, which could contain non-ASCII characters.  This routine
  produces 'utf8' unicode for str arguments.

  Args:
    xml_text: From GetText (str or unicode)

  Returns:
    unicode object
  """
  if type(xml_text) == unicode:
    return xml_text
  else:
    return unicode(xml_text, encoding=_DEFAULT_ENCODING)


def CopyStringNodes(model, node, names, name_map=None):
  """Copies XML nodes into string attributes of the same respective names.

  Args:
    model: db.Model object
    node: xml.dom.Node object
    names: List of child node / model attribute names (strings) that have
        StringProperty type.
    name_map: Dict to translate child node names to model attribute names
        (str:str)

  Returns:
    List of RecoverableError objects, possibly empty, representing multiple
    nodes that are found for any of the names, or if there is a problem
    converting the text into the appropriate value object.
  """
  return CopyNodes(model, node, names, ParseString, name_map)


def CopyStringNodeLists(model, node, names, name_map=None):
  """Copies multiple XML nodes into model list attributes.

  Args:
    model: db.Model object
    node: xml.dom.Node object
    names: List of child node / model attribute names (strings) that have
        StringProperty type.
    name_map: Dict to translate child node names to model attribute names
        (str:str)

  Returns:
    List of RecoverableError objects, possibly empty, representing problems
    converting the text into the appropriate value object.
  """
  return CopyNodeLists(model, node, names, ParseString, name_map)


def ParseText(xml_text):
  """Converts XML text into a db.Text object.

  Args:
    xml_text: From GetText (str or unicode)

  Returns:
    db.Text object
  """
  return db.Text(ParseString(xml_text))


def CopyTextNodes(model, node, names, name_map=None):
  """Copies XML nodes into model text attributes of the same respective names.

  Args:
    model: db.Model object
    node: xml.dom.Node object
    names: List of child node / model attribute names (strings) that have
        TextProperty type.

  Returns:
    List of RecoverableError objects, possibly empty, representing multiple
    nodes that are found for any of the names, or if there is a problem
    converting the text into the appropriate value object.
  """
  return CopyNodes(model, node, names, ParseText, name_map)


def CopyTextNodeLists(model, node, names, name_map=None):
  """Copies multiple XML nodes into model list attributes.

  Args:
    model: db.Model object
    node: xml.dom.Node object
    names: List of child node / model attribute names (strings) that have
        TextProperty type.
    name_map: Dict to translate child node names to model attribute names
        (str:str)

  Returns:
    List of RecoverableError objects, possibly empty, representing problems
    converting the text into the appropriate value object.
  """
  return CopyNodeLists(model, node, names, ParseText, name_map)


# Hi-resolution timestamps are not officially supported by ISO 8601, but they
# appear in some CAP's, like those in the USGS volcano feed.  This regex will
# extract the conforming portion.
HIRES_DATETIME = re.compile('^(\d{8}T\d{6})\.\d{3}Z$')


# Parse certain ISO 8601 timestamps that do not include delimiters between the
# components.  See below for TODO.
ISO_8601_WITHOUT_DELIMITERS = re.compile(
    '^(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)(\d\d)(.*)')


def ParseDateTime(xml_text):
  """Converts XML ISO 8601 date/time representation into datetime.

  Args:
    xml_text: ISO 8601 representation (string)

  Returns:
    datetime.datetime object

  Raises:
    ValueError: If xml_text is not a valid ISO 8601 representation.
  """
  # TODO(Matt Frantz): Figure out how to handle non-standard datetime formats.
  # Right now, we assume it is ISO 8601 compliant before trying other formats.
  try:
    return iso8601.parse_date(xml_text)
  except (TypeError, iso8601.ParseError):
    # TODO(Matt Frantz): When the iso8601 module supports all ISO 8601 formats,
    # we should just be able to simply drop the "without delimiters" portion.
    # But to workaround, we need to add delimiters.
    match = ISO_8601_WITHOUT_DELIMITERS.match(xml_text)
    if match:
      iso8601_without_delimiters = '%s-%s-%sT%s:%s:%s%s' % match.groups()
      logger.debug('ISO 8601 without delimiters: %r',
                   iso8601_without_delimiters)
      return iso8601.parse_date(iso8601_without_delimiters)
    else:
      raise ValueError('Invalid date-time representation: %r' % xml_text)


def CopyDateTimeNodes(model, node, names, name_map=None):
  """Copies XML nodes with date-time data into model attributes by name.

  Args:
    model: db.Model object
    node: xml.dom.Node object
    names: List of child node / model attribute names (strings) that have
        DateTimeProperty type.
    name_map: Dict to translate child node names to model attribute names
        (str:str)

  Returns:
    List of RecoverableError objects, possibly empty, representing multiple
    nodes that are found for any of the names, or if there is a problem
    converting the text into the appropriate value object.
  """
  return CopyNodes(model, node, names, ParseDateTime, name_map)


def CopyIntegerNodes(model, node, names, name_map=None):
  """Copies XML nodes with integer data into model attributes by name.

  Args:
    model: db.Model object
    node: xml.dom.Node object
    names: List of child node / model attribute names (strings) that have
        IntegerProperty type.
    name_map: Dict to translate child node names to model attribute names
        (str:str)

  Returns:
    List of RecoverableError objects, possibly empty, representing multiple
    nodes that are found for any of the names, or if there is a problem
    converting the text into the appropriate value object.
  """
  return CopyNodes(model, node, names, int, name_map)
