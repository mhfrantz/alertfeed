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

"""Datastore utilities."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import logging

try:
  from google.appengine.ext import db
except ImportError:
  from google3.apphosting.ext import db


# Allow independent control of the logging from this module.
logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)


def ModelAsDict(model_class, model):
  """Extracts db.Model properties as a dict.

  Args:
    model_class: db.Model subclass
    model: db.Model object

  Returns:
    Dict with attribute names as keys and attribute values as values.
  """
  props = {}
  for prop in model_class.properties().keys() + model.dynamic_properties():
    try:
      props[prop] = SafelyDereference(model, prop)
    except db.Error:
      # Sometimes, a reference attribute will fail to load because its
      # referent has been deleted.  Handle this gracefully.
      logger.warn('Unable to extract %s.%s from %r',
                  model_class.kind(), prop, model)

  logger.debug('ModelAsDict %s = %r', model_class.kind(), props)
  return props


def SafelyDereference(model, property_name):
  """Safely dereference a property that may be a Reference.

  Args:
    model: Model instance (db.Model)
    property_name: Name of the property, possibly a Reference (str)

  Returns:
    Referent object, or None if it was a Reference that would not resolve.

  Raises:
    db.Error: If anything other than dereferencing errors occur.
  """
  try:
    return getattr(model, property_name)
  except db.Error, e:
    if 'ReferenceProperty failed to be resolved' in str(e):
      model_name = model.__class__.kind()
      logging.error('Could not dereference "%s" property on %s model %s',
                    property_name, model_name, model.key())
      return None
    else:
      raise
