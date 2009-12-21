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

"""CAP parser for Datastore.

This module contains MakeDbAlertFromMem, which generate a Datastore model from
an in-memory representation (caplib) of a CAP alert.  The code in this module,
along with both model classes, must track the evolving CAP standard.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import datetime
import logging

try:
  import cap_schema
  import caplib_adapter
  import model_parser
except ImportError:
  # google3
  from google3.pyglib import logging

  from google3.dotorg.gongo.appengine_cap2kml import cap_schema
  from google3.dotorg.gongo.appengine_cap2kml import caplib_adapter
  from google3.dotorg.gongo.appengine_cap2kml import model_parser


def _ConvertDatetime(value):
  """Converts a caplib datetime subclass into a raw datetime.

  Args:
    value: Instance of subclass of datetime.datetime.

  Returns:
    datetime.datetime object
  """
  return value + datetime.timedelta(seconds=0)


def MakeDbAlertFromMem(alert_mem):
  """Creates a database model from a memory model of a CAP alert.

  Args:
    alert_mem: caplib.Alert object

  Returns:
    cap_schema.CapAlert object (populated, not saved)
  """
  alert_db = cap_schema.CapAlert()
  model_parser.AssignScalarAttrs(
      alert_db, alert_mem,
      ['identifier', 'sender', 'status', 'msgType', 'source', 'scope',
       'restriction'],
      caplib_adapter.ALERT_NAME_MAP, str)
  model_parser.AssignScalarAttrs(
      alert_db, alert_mem, ['sent'],
      caplib_adapter.ALERT_NAME_MAP, _ConvertDatetime)
  model_parser.AppendListAttrs(
      alert_db, alert_mem, ['code', 'references'],
      caplib_adapter.ALERT_NAME_MAP, str)

  for info in alert_mem.info:
    model_parser.AppendScalarAttrs(
        alert_db, info,
        ['language', 'urgency', 'severity', 'certainty', 'audience',
         'senderName', 'web', 'contact'],
        caplib_adapter.INFO_NAME_MAP, str)
    model_parser.AppendScalarAttrs(
        alert_db, info, ['effective', 'onset', 'expires'],
        caplib_adapter.INFO_NAME_MAP, _ConvertDatetime)
    model_parser.AppendListAttrs(
        alert_db, info, ['category', 'responseType'],
        caplib_adapter.INFO_NAME_MAP, str)

    for resource in info.resource:
      model_parser.AppendScalarAttrs(
          alert_db, resource, ['resourceDesc', 'mimeType', 'uri'],
          caplib_adapter.RESOURCE_NAME_MAP, str)
      model_parser.AppendScalarAttrs(
          alert_db, resource, ['size'],
          caplib_adapter.RESOURCE_NAME_MAP, long)

    for area in info.area:
      model_parser.AppendScalarAttrs(
          alert_db, area, ['altitude', 'ceiling'],
          caplib_adapter.AREA_NAME_MAP, float)

  return alert_db
