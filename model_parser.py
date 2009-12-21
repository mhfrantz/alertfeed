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

"""Library to support parsing plain-old-data models.

Parsing is implemented by copying and possibly transforming data from a
'source' model to a 'target' model.

The 'plain-old-data model' concept refers to objects with attributes that are
simple scalars or lists of scalars.  The actual type of a scalar attribute is
not prescribed by this module, and is never inferred by it.  There is no
dynamic type handling.  Instead, the application must have prior knowledge of
the attribute types.

This module includes routines for copying attributes from one model to another
with a different but related type.  The two types may share some set of common
attributes, with the association being made by attribute name, or via an
explicit attribute name_map.  The name_map contains target attribute names as
keys and source attribute names as values.

The types of each associated attribute are constrained.  If the source
attribute is of a scalar type, then the corresponding target attribute must be
of scalar or list type.  If the source attribute is of list type, the
corresponding target attribute must also be of list type.

  AssignScalarAttrs: scalar to scalar
  AppendListAttrs: list to list
  AppendScalarAttrs: scalar to list

By default, the corresponding scalar types must be equivalent.  However, with
the option of using a scalar type 'converter', the application can transform
the attribute values from source type to target type.

Failure to parse an individual attribute does not raise an exception.
Instead, all exceptions are logged with the exception of
DeadlineExceededError, which is propagated.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import logging
import traceback

try:
  from google.appengine.runtime import DeadlineExceededError
except ImportError:
  # google3
  from google3.apphosting.runtime.apiproxy_errors import DeadlineExceededError
  from google3.pyglib import logging


def AssignScalarAttrs(target, source, attr_names, name_map, converter):
  """Assigns scalar source attributes to scalar target attributes.

  Args:
    target: Target model object
    source: Source model object
    attr_names: List of attribute names (list of str)
    name_map: Dict to translate target attr names to source attribute names
        (str:str)
    converter: Function which converts a source attribute to its target form.
  """
  def Do(attr_name):
    if attr_name in name_map:
      source_attr_name = name_map[attr_name]
    else:
      source_attr_name = attr_name

    if hasattr(source, source_attr_name):
      attr = getattr(source, source_attr_name)
      attr = converter(attr)
      setattr(target, attr_name, attr)

  _SafeIterate(attr_names, Do)


def AppendListAttrs(target, source, attr_names, name_map, converter):
  """Appends each element of the source attributes to target attributes.

  Args:
    target: Target model object
    source: Source model object
    attr_names: List of attribute names (list of str)
    name_map: Dict to translate target attr names to source attribute names
        (str:str)
    converter: Function which converts a source attribute to its target form.
  """
  def Do(attr_name):
    if attr_name in name_map:
      source_attr_name = name_map[attr_name]
    else:
      source_attr_name = attr_name

    source_list = getattr(source, source_attr_name)
    target_list = getattr(target, attr_name)
    for attr in source_list:
      attr = converter(attr)
      target_list.append(attr)

  _SafeIterate(attr_names, Do)


def AppendScalarAttrs(target, source, attr_names, name_map, converter):
  """Appends the source attributes to target attributes.

  Args:
    target: Target model object
    source: Source model object
    attr_names: List of attribute names (list of str)
    name_map: Dict to translate target attr names to source attribute names
        (str:str)
    converter: Function which converts a source attribute to its target form.
  """
  def Do(attr_name):
    if attr_name in name_map:
      source_attr_name = name_map[attr_name]
    else:
      source_attr_name = attr_name

    if hasattr(source, source_attr_name):
      attr = getattr(source, source_attr_name)
      attr = converter(attr)
      target_list = getattr(target, attr_name)
      target_list.append(attr)

  _SafeIterate(attr_names, Do)


def _SafeIterate(args, do):
  """Vists each attribute name.

  Traps and logs errors on each element.

  Args:
    args: Iterable of arguments.
    do: Functor that accepts each argument.
  """
  for arg in args:
    try:
      do(arg)
    except (DeadlineExceededError, AssertionError):
      raise
    except Exception, e:
      logging.debug('%s', traceback.format_exc())
      logging.error(e)
