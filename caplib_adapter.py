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

"""Adapts attribute name for caplib to CAP element names.

For some reason, the third party caplib module does not always name its
attributes according to the CAP element names.  This module contains maps for
these exceptional attribute names.  Each map contains CAP element names as
keys and caplib attribute names as values.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'


# caplib.Alert attributes
ALERT_NAME_MAP = {'code': 'codes'}

# caplib.Info attributes
INFO_NAME_MAP = {'responseType': 'response'}

# caplib.Resource attributes
RESOURCE_NAME_MAP = {'resourceDesc': 'description',
                     'mimeType': 'mimetype'}

# caplib.Area attributes
AREA_NAME_MAP = {'areaDesc': 'description'}
