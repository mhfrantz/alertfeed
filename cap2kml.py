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

"""Converts CAP alerts to KML placemarks.

Based on code in experimental/users/bent/cap2kml/cap2kml, especially
cap_alert.h and cap_util.cc.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import logging
import re

# Third party
import pyfo

from google.appengine.runtime import DeadlineExceededError


class Error(Exception):
  pass


class MultipleInfoError(Error):
  pass


def Kml(nodes):
  """Returns a tuple representing a KML Document node.

  Args:
    nodes: Iterable of child nodes representing top-level KML objects.

  Returns:
    Tuple for pyfo to produce the <kml> node.
  """
  return ('kml', ('Document', nodes),
          dict(xmlns='http://www.opengis.net/kml/2.2'))


class CapAlertAsKmlPlacemark(object):
  """Converts CAP alerts to KML Placemarks."""

  # Cap.status values that will become visible placemarks.
  VISIBLE_STATUS = frozenset(['Actual'])

  # Cap.status values that will become invisible placemarks.
  INVISIBLE_STATUS = frozenset(['Exercise', 'System', 'Test', 'Draft'])

  # Cap.msgType values that will become visible placemarks.
  VISIBLE_MSG_TYPES = frozenset(['Alert', 'Update'])

  # Cap.msgType values that will become invisible placemarks.
  INVISIBLE_MSG_TYPES = frozenset(['Update', 'Cancel', 'Ack', 'Error'])

  def __init__(self, cap):
    """Initializes CapAlertAsKmlPlacemark.

    Args:
      cap: caplib.Alert object
    """
    self.name = None
    self.description = None
    self.visibility = None
    self.style_url = None
    self.icon_url = None
    self.geometries = []
    self.atom_link_url = None
    # Extract data from the Cap object.
    if hasattr(cap, 'identifier') and cap.identifier:
      self.name = cap.identifier
    if hasattr(cap, 'status') and cap.status:
      self._SetStatus(cap.status)
    if hasattr(cap, 'msgType') and cap.msgType:
      self._SetMsgType(cap.msgType)
    if hasattr(cap, 'scope') and cap.scope:
      self._SetScope(cap.scope)

    infos = list(cap.info)
    if infos:
      if len(infos) > 1:
        raise MultipleInfoError(str(cap))
      self._SetInfo(infos[0])
    else:
      logging.warn('No Cap.info: %s', cap)

  def ToKml(self):
    """Returns pyfo-compatible data structure for a Placemark node.

    Returns:
      Dict for pyfo to produce the Placemark node, or None if there is not
      enough valid data to produce a Placemark node.
    """
    placemark = []
    if self.name:
      placemark.append(('name', self.name))
    if self.description:
      placemark.append(('description', self.description))
    if self.visibility is not None:
      placemark.append(('visibility', self.visibility))
    if self.style_url:
      placemark.append(('styleUrl', self.style_url))
    if self.icon_url:
      placemark.append(_Icon(self.icon_url))
    if self.geometries:
      placemark.append(_MultiGeometry(self.geometries))
    if self.atom_link_url:
      placemark.append(_AtomLink(self.atom_link_url))
    if placemark:
      placemark = ('Placemark', placemark)
      _DebugPyfo(placemark)
      return placemark
    else:
      return None

  def _SetStatus(self, status):
    """Incorporates the CAP alert status.

    Args:
      status: CAP Alert status (string)
    """
    if status in self.VISIBLE_STATUS:
      self.visibility = 1
    elif status in self.INVISIBLE_STATUS:
      self.visibility = 0
    else:
      logging.warn('Unrecognized CAP Alert status "%s"', status)

  def _SetMsgType(self, msg_type):
    """Incorporates the CAP alert message type.

    Args:
      msg_type: CAP Alert message type (string)
    """
    if msg_type in self.VISIBLE_MSG_TYPES:
      self.visibility = 1
    elif msg_type in self.INVISIBLE_MSG_TYPES:
      self.visibility = 0
    else:
      logging.warn('Unrecognized CAP Alert message type "%s"', msg_type)

  def _SetScope(self, scope):
    """Incorporates the CAP alert scope.

    Args:
      scope: CAP Alert scope (string)
    """
    if scope in frozenset(['Public', 'Restricted', 'Private']):
      # TODO(Matt Frantz): Incorporate scope.
      pass
    else:
      logging.warn('Unrecognized CAP Alert scope "%s"', scope)

  def _SetInfo(self, info):
    """Incorporates CAP info data.

    Args:
      info: caplib.Info object
    """
    if hasattr(info, 'category') and info.category:
      self._AddCategories(info.category)
    if hasattr(info, 'severity') and info.severity:
      self._SetSeverity(info.severity)
    if hasattr(info, 'description') and info.description:
      self.description = info.description
    areas = info.area
    if areas:
      for area in areas:
        self._AddArea(area)
    else:
      logging.warn('No CapInfo.area: %s', info)

  # Icons (as URL's) for each known CapInfo.category.
  _CATEGORY_ICONS = {
      'Geo': 'http://maps.google.com/mapfiles/kml/shapes/earthquake.png',
      'Met': 'http://maps.google.com/mapfiles/kml/shapes/rainy.png',
      'Safety': 'http://maps.google.com/mapfiles/kml/shapes/police.png',
      'Security': 'http://maps.google.com/mapfiles/kml/shapes/caution.png',
      'Rescue': '',
      'Fire': '',
      'Health': '',
      'Env': '',
      'Transport': '',
      'Infra': '',
      'CBRNE': '',
      'Other': '',
      }

  def _AddCategories(self, categories):
    """Incorporates the CapInfo categories.

    If there are multiple categories, the first recognized one will be used.

    Args:
      categories: CAP alert info categories (iterable of str)
    """
    for category in categories:
      if category in self._CATEGORY_ICONS:
        self.icon_url = self._CATEGORY_ICONS[category]
        return
      else:
        logging.warn('Unrecognized CAP Alert Info category "%s"', category)

  # Styles for each known CapInfo.severity.
  _SEVERITY_STYLES = {
      'Extreme': 'stylesheets/style.kml#extreme',
      'Severe': 'stylesheets/style.kml#severe',
      'Moderate': 'stylesheets/style.kml#moderate',
      'Minor': 'stylesheets/style.kml#minor',
      'Unknown': 'stylesheets/style.kml#unknown',
      }

  def _SetSeverity(self, severity):
    """Incorporates CAP Alert Info severity data.

    Args:
      severity: CAP Alert Info severity (string)
    """
    if severity in self._SEVERITY_STYLES:
      self.style_url = self._SEVERITY_STYLES[severity]
    else:
      logging.warn('Unrecognized CAP Alert Info severity "%s"', severity)

  def _AddArea(self, area):
    """Incorporates CAP Alert Info Area data.

    Args:
      area: caplib.Area object
    """
    for circle in area.circle:
      self._AddCircle(circle)
    for polygon in area.polygon:
      self._AddPolygon(polygon)

  def _AddCircle(self, circle):
    """Incorporates a single CAP Alert Info Area circle.

    Args:
      circle: caplib.Circle
    """
    geometry = _CapCircleToKml(circle)
    if geometry:
      _DebugPyfo(geometry)
      self.geometries.append(geometry)

  def _AddPolygon(self, polygon):
    """Incorporates a single CAP Alert Info Area polygon.

    Args:
      polygon: caplib.Polygon
    """
    geometry = _CapPolygonToKml(polygon)
    if geometry:
      _DebugPyfo(geometry)
      self.geometries.append(geometry)


def _Icon(icon_url):
  icon = ('Style', ('IconStyle', ('Icon', ('href', icon_url))))
  _DebugPyfo(icon)
  return icon


def _MultiGeometry(geometries):
  multi = ('MultiGeometry', geometries)
  _DebugPyfo(multi)
  return multi


def _AtomLink(url):
  atom_link = ('atom:link', None, dict(href=url))
  _DebugPyfo(atom_link)
  return atom_link


def _Point(cap_point):
  """Forms a KML Point.

  Args:
    cap_point: caplib.Point

  Returns:
    Object for pyfo to make a KML Point node
  """
  point = ('Point', _Coordinates([cap_point]))
  _DebugPyfo(point)
  return point


def _Coordinates(points):
  """Forms a KML coordinates note.

  Args:
    points: List of caplib.Point objects.

  Returns:
    Object for pyfo to make a KML coordinates node
  """
  point_strings = []
  for point in points:
    # Note that KML is lon, lat[, alt].  We don't specify altitude because CAP
    # has a 2-D "on the Earth's surface) geometry model.
    point_string = '%f,%f' % (point.longitude, point.latitude)
    point_strings.append(point_string)

  coordinates = ('coordinates', ' '.join(point_strings))
  _DebugPyfo(coordinates)
  return coordinates


def _CapCircleToKml(cap_circle):
  """Parses a CAP Alert Info Area Circle into a KML geometry object.

  CAP circle is a string containing a center point (pair of comma-delimited
  floating point numbers), and a radius, with a whitespace delimiter.

  Based on cap_util.cc:CapCircleToKml.

  Args:
    circle: caplib.Circle

  Returns:
    Tuple for pyfo to produce a KML geometry node, or None if parse error.
  """
  try:
    # TODO(Matt Frantz): What is the unit of radius in a CAP circle?
    # TODO(Matt Frantz): Use the radius to make a KML circle.
    return _Point(cap_circle.point)
  except (DeadlineExceededError, AssertionError):
    raise
  except Exception, e:
    logging.warn('Invalid CAP circle format "%s": %r', cap_circle, e)
    return None


def _CapPolygonToKml(cap_polygon):
  """Parses a CAP Alert Info Area Polygon into a KML geometry object.

  CAP polygon is a string containing ...

  Based on cap_util.cc:CapPolygonToKml.

  Args:
    cap_polygon: caplib.Polygon

  Returns:
    Tuple for pyfo to produce a KML geometry node, or None if parse error.
  """
  try:
    # CAP specifies latitude and longitude in decimal degrees, following
    # WGS-84, so no coordinate transformation is required.
    vertices = list(cap_polygon)
    polygon = ('Polygon', ('outerBoundaryIs',
                           ('LinearRing', _Coordinates(vertices))))
    _DebugPyfo(polygon)
    return polygon
  except (DeadlineExceededError, AssertionError):
    raise
  except Exception, e:
    logging.warn('Invalid CAP polygon format "%s": %r', cap_polygon, e)
    return None


def _DebugPyfo(node):
  """Conditionally asserts that the node can be converted to XML with pyfo.

  Args:
    node: Any object that pyfo can convert to XML
  """
  if logging.getLogger().level >= logging.DEBUG:
    try:
      logging.debug('XML = %s', pyfo.pyfo(node))
    except DeadlineExceededError:
      raise
    except:
      logging.error('Unable to Pyfo: %r', node)
