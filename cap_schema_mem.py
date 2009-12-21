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

"""CAP schema for in-memory models.

This module defines several shadow classes which extend existing caplib
classes.  The purpose is twofold:

(1) To adapt the cap_parse_mem.MemoryCapParser code to the caplib API.
    Specifically, for some properties that are represented as CAP-specific
    objects rather than generic scalar types (string, datetime, etc.), the
    shadow classes can accept the generic scalars that CapParser will present.

(2) To provide filtering of nodes via web_query.

An example is the handling of the CAP circle element (part of Area).  In XML,
circles are strings with a specific format.  CapParser simply parses the
string from the XML and attempts to insert it into the corresponding list
property as a string.  The default caplib.Area.circle property is of type
ListProperty(ObjectList, Circle).  Such a property accepts only Circle
objects, so the string insertion would fail.

Enter ShadowArea, which extends caplib.Area and overrides the definition of
the circle property.  It uses ShadowObjectList, which contains a special
'append' method that allows for the transformation of non-Circle objects (such
as strings) into Circle objects.  More precisely, it transforms them into
ShadowCircle objects, which extend caplib.Circle.  The ShadowCircle
constructor accepts the string argument and parses it into a point and radius
using caplib.Circle.fromString, before continuing with the Circle constructor.

The result is that the MemoryCapParser produces, in some cases, Shadow*
classes (defined in this module) in place of certain caplib classes.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'


try:
  import google3
  import cap as caplib
except ImportError:
  import cap as caplib


def FilteredList(model_name):
  """Returns a class that works as a caplib ContainerList with a filter.

  This is a class factory.  It binds a particular Datastore model as the
  predicate selector for a web_query.Query.  Instances of this class must be
  attached to Shadow* objects (e.g. ShadowInfo) that have a _query member
  containing a web_query.Query object.

  Args:
    model_name: Datastore model name whose predicates will be applied to the
        items in the list (str).

  Returns:
    Class object, a subclass of caplib.ContainerList.
  """

  class TheList(caplib.ContainerList):
    """A container of objects to be filtered."""

    def __init__(self, parent, cls, listobj=None):
      """Initializes a TheList object.

      Args:
        parent: Shadow* object (e.g. ShadowInfo) that has a _query attribute
            containing a web_query.Query object.
        cls: Class object for the elements of the list.
        listobj: List to copy from, or None to initialize an empty list.
      """
      super(TheList, self).__init__(parent, cls, listobj)
      self.__model_name = model_name

    def __Query(self):
      """Determines if the deferred query applies to this list.

      Returns:
        web_query.Query, iff the query has predicates relevant to this list.
      """
      query = self._parent._query
      if query and self.__model_name in query.models:
        return query
      else:
        return None

    def __len__(self):
      """Returns the number of elements (filtered)."""
      query = self.__Query()
      if query:
        # We must iterate to see which ones apply.
        return len(list(iter(self)))
      else:
        return super(TheList, self).__len__()

    def __iter__(self):
      """Filters the elements through the query, if necessary."""
      query = self.__Query()
      if query:
        models = []
        for model in super(TheList, self).__iter__():
          if query.PermitsModel(model_name, model):
            models.append(model)
        return iter(models)
      else:
        return super(TheList, self).__iter__()

    def __contains__(self, obj):
      """Determines if an object is in the filtered list."""
      query = self.__Query()
      if query:
        # We must iterate to see which ones apply.
        return obj in list(self)
      else:
        return super(TheList, self).__contains__(obj)

  return TheList


# Instantiate the FilteredList for the only Datastore type that we care about
# (at least for now).
FilteredListForCapAlert = FilteredList('CapAlert')


class ShadowReference(caplib.Reference):
  """Overrides the Reference constructor to accept CAP V1.0 string."""

  def __init__(self, text):
    """Initializes a ShadowReference instance.

    Args:
      text: Compatible with CAP V1.1 or V1.0 (str)
    """
    try:
      super(ShadowReference, self).__init__(text)
    except ValueError:
      try:
        identifier, sender = text.split('/', 1)
      except ValueError:
        raise ValueError('Invalid alert reference: %r', text)
      self._sender = caplib.Sender(sender)
      self._identifier = caplib.Identifier(identifier)
      self._sent = caplib.Sent(None)  # TODO(Matt Frantz): This becomes now!


class ShadowCircle(caplib.Circle):
  """Overrides the Circle constructor to accept a string that is parsed."""

  def __init__(self, text):
    """Initializes a ShadowCircle instance.

    Args:
      text: Compatible with caplib.Circle.fromString (str)
    """
    that = caplib.Circle.fromString(text)
    super(ShadowCircle, self).__init__(that.point, that.radius)


class ShadowPolygon(caplib.Polygon):
  """Overrides the Polygon constructor to accept a string that is parsed."""

  def __init__(self, text):
    """Initializes a ShadowPolygon instance.

    Args:
      text: Compatible with caplib.Polygon.fromString (str)
    """
    that = caplib.Polygon.fromString(text)
    super(ShadowPolygon, self).__init__(list(that))


class ShadowObjectList(caplib.ObjectList):
  """An adapter that permits transformation in the append method."""

  def append(self, value):
    """Appends the value to the list, after possibly converting it.

    Args:
      value: Either an instance of the permitted type, or an object that is
      accepted by the constructor of the permitted type.
    """
    # If the value is not an object of the correct type, try to construct one
    # from it.
    if not isinstance(value, self._cls):
      value = self._cls(value)
    super(ShadowObjectList, self).append(value)


class ShadowArea(caplib.Area):
  """Override certain properties to make them more permissive."""

  polygon = caplib.ListProperty(ShadowObjectList, ShadowPolygon)
  circle = caplib.ListProperty(ShadowObjectList, ShadowCircle)


class ShadowResource(caplib.Resource):
  pass


class ShadowInfo(caplib.Info):
  """Override certain properties to shadow subordinate elements."""

  def __init__(self, template=None, query=None):
    super(ShadowInfo, self).__init__(template=template)
    self._query = query

  area = caplib.ListProperty(FilteredListForCapAlert, ShadowArea)
  resource = caplib.ListProperty(FilteredListForCapAlert, ShadowResource)


class ShadowAlert(caplib.Alert):
  """Overrides certain properties to make them more permissive."""

  def __init__(self, template=None, query=None):
    super(ShadowAlert, self).__init__(template)
    self._query = query

  references = caplib.ListProperty(caplib.ReferenceList, ShadowReference)
  info = caplib.ListProperty(FilteredListForCapAlert, ShadowInfo)
