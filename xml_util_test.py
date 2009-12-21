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

"""Tests for xml_util."""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

import datetime
import re
from xml.dom import minidom

import google3

import cap as caplib
import iso8601
import mox

from google3.apphosting.ext import db
from google3.pyglib import app
from google3.testing.pybase import googletest
from google3.dotorg.gongo.appengine_cap2kml import db_util
from google3.dotorg.gongo.appengine_cap2kml import xml_util


# Haul the exception class symbol into this module for convenience.
DeadlineExceededError = xml_util.DeadlineExceededError


def ParseXml(xml_string, node_name):
  """Parses XML and returns the specified nodes.

  Args:
    xml_string: XML document (str)
    node_name: Tag name of the nodes (str)

  Returns:
    List of xml.dom.Node objects
  """
  document = minidom.parseString(xml_string)
  return document.getElementsByTagName(node_name)


class XmlUtilTestBase(mox.MoxTestBase):
  """Test case base class for xml_util tests."""

  def setUp(self):
    super(XmlUtilTestBase, self).setUp()
    # Allow testing of logging.
    self.mox.StubOutWithMock(xml_util, 'logging')
    self.mox.StubOutWithMock(xml_util, 'logger')

  def assertReturnsErrorWithRegexpMatch(self, exception_class, regexp, function,
                                        *args, **kwargs):
    """Checks that an error is returned from a CopyNodes-like function.

    The function is expected to return a list of objects.  At least one object
    in the list must be of type exception_class, and its string representation
    must match regexp.

    Args:
      exception_class: Type of error to find (class).
      regexp: Regular expression string to match (str)
      function: Function to invoke (callable)
      args: Positional arguments for the function
      kwargs: Keyword arguments for the function
    """
    errors = function(*args, **kwargs)
    pattern = re.compile(regexp)
    for error in errors:
      if isinstance(error, exception_class):
        if pattern.match(str(error)):
          return

    self.fail('Expected error %s matching %s not found: %r' %
              (exception_class, regexp, [str(x) for x in errors]))


class XmlUtilTest(XmlUtilTestBase):
  """Tests for miscellaneous functions in xml_util."""

  def testNodeToString(self):
    self.mox.ReplayAll()
    xml_string = (
        '<?xml version="1.0" ?><foo a="1">bar</foo>')
    node = minidom.parseString(xml_string)
    self.assertEquals(str(xml_util.NodeToString(node)), xml_string)

  def testGetText_fromEmptyList(self):
    self.mox.ReplayAll()
    self.assertEquals(xml_util.GetText([]), '')

  def testGetText_fromOneNodeWithText(self):
    self.mox.ReplayAll()
    nodes = ParseXml('<?xml version="1.0" ?><foo a="1">bar</foo>', 'foo')
    self.assertEquals(len(nodes), 1)
    self.assertEquals(xml_util.GetText(nodes), '')
    foo_node = nodes[0]
    self.assertEquals(xml_util.GetText(foo_node.childNodes), 'bar')

  def testGetText_fromOneNodeWithoutText(self):
    self.mox.ReplayAll()
    nodes = ParseXml('<?xml version="1.0" ?><foo a="1"/>', 'foo')
    self.assertEquals(len(nodes), 1)
    self.assertEquals(xml_util.GetText(nodes), '')
    foo_node = nodes[0]
    self.assertEquals(xml_util.GetText(foo_node.childNodes), '')

  def testGetText_fromMultipleNodes(self):
    self.mox.ReplayAll()
    nodes = ParseXml("""
        <?xml version="1.0" ?>
        <list>
          <foo a="1">bar</foo>
          <foo a="1">baz</foo>
        </list>
        """.strip(), 'foo')
    self.assertEquals(len(nodes), 2)
    self.assertEquals(xml_util.GetText(nodes), '')
    child_nodes = []
    for node in nodes:
      child_nodes.extend(node.childNodes)
    self.assertEquals(xml_util.GetText(child_nodes), 'barbaz')

  def testParseString_unicode(self):
    self.mox.ReplayAll()
    u = unicode('foo', encoding='latin1')
    self.assertEquals(xml_util.ParseString(u), u)

  def testParseString_str(self):
    self.mox.ReplayAll()
    self.assertEquals(xml_util.ParseString('foo'),
                      unicode('foo', encoding=xml_util._DEFAULT_ENCODING))

  def testCopyStringNodes(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'string1', 'bar')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <string1>bar</string1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyStringNodes(model, nodes[0], FOO_NAMES)
    self.assertEquals(model.string1,
                      unicode('bar', encoding=xml_util._DEFAULT_ENCODING))

  def testCopyStringNodes_withNameMap(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'string2', 'bar')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <string1>bar</string1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyStringNodes(model, nodes[0], FOO_NAMES,
                             name_map={'string1': 'string2'})
    self.assertEquals(model.string1, None)
    self.assertEquals(model.string2,
                      unicode('bar', encoding=xml_util._DEFAULT_ENCODING))

  def testCopyStringNodeLists(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'string_list1', 'bar1')
    xml_util.logger.debug(mox.IgnoreArg(), 'string_list1', 'bar2')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <string_list1>bar1</string_list1>
          <string_list1>bar2</string_list1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyStringNodeLists(model, nodes[0], FOO_NAMES)
    self.assertListEqual(model.string_list1,
                         [unicode('bar1', encoding=xml_util._DEFAULT_ENCODING),
                          unicode('bar2', encoding=xml_util._DEFAULT_ENCODING)])

  def testCopyStringNodeLists_withNameMap(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'string_list2', 'bar1')
    xml_util.logger.debug(mox.IgnoreArg(), 'string_list2', 'bar2')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <string_list1>bar1</string_list1>
          <string_list1>bar2</string_list1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyStringNodeLists(model, nodes[0], FOO_NAMES,
                                 name_map={'string_list1': 'string_list2'})
    self.assertListEqual(model.string_list1, [])
    self.assertListEqual(model.string_list2,
                         [unicode('bar1', encoding=xml_util._DEFAULT_ENCODING),
                          unicode('bar2', encoding=xml_util._DEFAULT_ENCODING)])

  def testParseText_unicode(self):
    self.mox.ReplayAll()
    u = unicode('foo', encoding='latin1')
    self.assertEquals(xml_util.ParseText(u), db.Text(u))

  def testParseText_str(self):
    self.mox.ReplayAll()
    self.assertEquals(
        xml_util.ParseText('foo'),
        db.Text(unicode('foo', encoding=xml_util._DEFAULT_ENCODING)))

  def testCopyTextNodes(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'text1', 'bar')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <text1>bar</text1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyTextNodes(model, nodes[0], FOO_NAMES)
    self.assertEquals(
        model.text1,
        db.Text(unicode('bar', encoding=xml_util._DEFAULT_ENCODING)))

  def testCopyTextNodes_withNameMap(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'text2', 'bar')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <text1>bar</text1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyTextNodes(model, nodes[0], FOO_NAMES,
                           name_map={'text1': 'text2'})
    self.assertEquals(model.text1, None)
    self.assertEquals(
        model.text2,
        db.Text(unicode('bar', encoding=xml_util._DEFAULT_ENCODING)))

  def testCopyTextNodeLists(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list1', 'bar1')
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list1', 'bar2')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <text_list1>bar1</text_list1>
          <text_list1>bar2</text_list1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyTextNodeLists(model, nodes[0], FOO_NAMES)
    self.assertListEqual(
        model.text_list1,
        [db.Text(unicode('bar1', encoding=xml_util._DEFAULT_ENCODING)),
         db.Text(unicode('bar2', encoding=xml_util._DEFAULT_ENCODING))])

  def testCopyTextNodeLists_withNameMap(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list2', 'bar1',)
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list2', 'bar2')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <text_list1>bar1</text_list1>
          <text_list1>bar2</text_list1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyTextNodeLists(model, nodes[0], FOO_NAMES,
                               name_map={'text_list1': 'text_list2'})
    self.assertListEqual(model.text_list1, [])
    self.assertListEqual(
        model.text_list2,
        [db.Text(unicode('bar1', encoding=xml_util._DEFAULT_ENCODING)),
         db.Text(unicode('bar2', encoding=xml_util._DEFAULT_ENCODING))])

  def testCopyDateTimeNodes(self):
    xml_util.logger.debug(
        mox.IgnoreArg(), 'datetime1', '2009-07-31T14:17:19+08:00')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <datetime1>2009-07-31T14:17:19+08:00</datetime1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyDateTimeNodes(model, nodes[0], FOO_NAMES)
    self.assertEquals(
        model.datetime1,
        datetime.datetime(2009, 7, 31, 14, 17, 19,
                          tzinfo=iso8601.FixedOffset(8, 0, None)))

  def testCopyDateTimeNodes_withNameMap(self):
    xml_util.logger.debug(
        mox.IgnoreArg(), 'datetime2', '2009-07-31T14:17:19+08:00')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <datetime1>2009-07-31T14:17:19+08:00</datetime1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyDateTimeNodes(model, nodes[0], FOO_NAMES,
                               name_map={'datetime1': 'datetime2'})
    self.assertEquals(model.datetime1, None)
    self.assertEquals(
        model.datetime2,
        datetime.datetime(2009, 7, 31, 14, 17, 19,
                          tzinfo=iso8601.FixedOffset(8, 0, None)))

  def testCopyIntegerNodes(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'integer1', '123')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <integer1>123</integer1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyIntegerNodes(model, nodes[0], FOO_NAMES)
    self.assertEquals(model.integer1, 123)

  def testCopyIntegerNodes_withNameMap(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'integer2', '123')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <integer1>123</integer1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyIntegerNodes(model, nodes[0], FOO_NAMES,
                              name_map={'integer1': 'integer2'})
    self.assertEquals(model.integer1, None)
    self.assertEquals(model.integer2, 123)


class ParseDateTimeTest(XmlUtilTestBase):
  """Tests for xml_util.ParseDateTime."""

  def testParseDateTime_invalid(self):
    self.mox.ReplayAll()
    self.assertRaisesWithRegexpMatch(
        ValueError, 'Invalid date-time representation',
        xml_util.ParseDateTime, 'xyz')

  def testParseDateTime_iso8601(self):
    self.mox.ReplayAll()
    self.assertEquals(
        xml_util.ParseDateTime('2009-07-31T14:17:19+08:00'),
        datetime.datetime(2009, 7, 31, 14, 17, 19,
                          tzinfo=iso8601.FixedOffset(8, 0, None)))

  def testParseDateTime_iso8601hiRes(self):
    self.mox.ReplayAll()
    self.assertEquals(
        xml_util.ParseDateTime('2009-07-31T14:17:19.123456-05:15'),
        datetime.datetime(2009, 7, 31, 14, 17, 19, 123456,
                          tzinfo=iso8601.FixedOffset(-5, -15, None)))

  def testParseDateTime_iso8601withoutDelimiters(self):
    xml_util.logger.debug(mox.StrContains('ISO 8601 without delimiters'),
                          '2009-07-31T14:17:19+08:00')
    self.mox.ReplayAll()

    self.assertEquals(
        xml_util.ParseDateTime('20090731T141719+08:00'),
        datetime.datetime(2009, 7, 31, 14, 17, 19,
                          tzinfo=iso8601.FixedOffset(8, 0, None)))

  def testParseDateTime_iso8601hiResWithoutDelimiters(self):
    xml_util.logger.debug(mox.StrContains('ISO 8601 without delimiters'),
                          '2009-07-31T14:17:19.123456-05:15')
    self.mox.ReplayAll()

    self.assertEquals(
        xml_util.ParseDateTime('20090731T141719.123456-05:15'),
        datetime.datetime(2009, 7, 31, 14, 17, 19, 123456,
                          tzinfo=iso8601.FixedOffset(-5, -15, None)))

  def testParseDateTime_iso8601withoutTimeZone(self):
    self.mox.ReplayAll()
    self.assertEquals(
        xml_util.ParseDateTime('2009-07-31T14:17:19'),
        datetime.datetime(2009, 7, 31, 14, 17, 19, tzinfo=iso8601.UTC))

  def testParseDateTime_iso8601hiResWithoutTimeZone(self):
    self.mox.ReplayAll()
    self.assertEquals(
        xml_util.ParseDateTime('2009-07-31T14:17:19.123456'),
        datetime.datetime(2009, 7, 31, 14, 17, 19, 123456, tzinfo=iso8601.UTC))


class ReferentModel(db.Model):
  """Test model to which references can be made."""
  pass


class FooModel(db.Model):
  """Test model containing various types of properties."""
  string1 = db.StringProperty()
  string2 = db.StringProperty()
  text1 = db.TextProperty()
  text2 = db.TextProperty()
  key1 = db.ReferenceProperty(ReferentModel, collection_name='foo1_set')
  key2 = db.ReferenceProperty(ReferentModel, collection_name='foo2_set')
  integer1 = db.IntegerProperty()
  integer2 = db.IntegerProperty()
  datetime1 = db.DateTimeProperty()
  datetime2 = db.DateTimeProperty()

  string_list1 = db.StringListProperty()
  string_list2 = db.StringListProperty()
  integer_list1 = db.ListProperty(int)
  integer_list2 = db.ListProperty(int)
  text_list1 = db.ListProperty(db.Text)
  text_list2 = db.ListProperty(db.Text)
  key_list1 = db.ListProperty(db.Key)
  key_list2 = db.ListProperty(db.Key)


# Names of the properties in FooModel.
FOO_NAMES = sorted(FooModel.properties().keys())


class CopyNodesTest(XmlUtilTestBase):
  """Tests for the CopyNodes method."""

  def testCopyNodes_withNoChildNodes(self):
    self.mox.ReplayAll()
    nodes = ParseXml('<?xml version="1.0" ?><foo/>', 'foo')
    model = FooModel()
    original_dict = db_util.ModelAsDict(FooModel, model)
    xml_util.CopyNodes(model, nodes[0], FOO_NAMES,
                       lambda x: self.assertNotEquals(x, x))
    self.assertDictEqual(db_util.ModelAsDict(FooModel, model), original_dict)

  def testCopyNodes_withDuplicateChildNodes(self):
    self.mox.ReplayAll()
    nodes = ParseXml('<?xml version="1.0" ?><foo><text1/><text1/></foo>', 'foo')
    model = FooModel()
    self.assertReturnsErrorWithRegexpMatch(
        xml_util.MultipleNodeError, 'Duplicate child node',
        xml_util.CopyNodes, model, nodes[0], FOO_NAMES,
        lambda x: self.assertNotEquals(x, x))

  def testCopyNodes_withEmptyText(self):
    self.mox.ReplayAll()
    nodes = ParseXml('<?xml version="1.0" ?><foo><text1/><text2/></foo>', 'foo')
    model = FooModel()
    original_dict = db_util.ModelAsDict(FooModel, model)
    xml_util.CopyNodes(model, nodes[0], FOO_NAMES,
                       lambda x: self.assertNotEquals(x, x))
    self.assertDictEqual(db_util.ModelAsDict(FooModel, model), original_dict)

  def testCopyNodes_DeadlineExceededError(self):
    self.mox.StubOutWithMock(xml_util, 'GetText')
    xml_util.GetText(mox.IgnoreArg()).AndRaise(DeadlineExceededError)
    self.mox.ReplayAll()

    nodes = ParseXml('<?xml version="1.0" ?><foo><text1/><text2/></foo>', 'foo')
    model = FooModel()
    self.assertRaises(DeadlineExceededError,
                      xml_util.CopyNodes, model, nodes[0], FOO_NAMES,
                      lambda x: self.assertNotEquals(x, x))

  def testCopyNodes_withNominalData(self):
    # Logged values are unconverted.
    xml_util.logger.debug(mox.IgnoreArg(), 'text1', 'go')
    xml_util.logger.debug(mox.IgnoreArg(), 'text2', 'bo')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <text1>go</text1>
          <text2>bo</text2>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyNodes(model, nodes[0], FOO_NAMES, lambda x: x + 'o')
    self.assertEquals(model.text1, 'goo')
    self.assertEquals(model.text2, 'boo')

  def testCopyNodes_withNameMap(self):
    # If it's not in the name map, the name stays the same.
    xml_util.logger.debug(mox.IgnoreArg(), 'string1', 'fo')
    # Logged values are post-name-mapping.
    xml_util.logger.debug(mox.IgnoreArg(), 'text2', 'go')
    xml_util.logger.debug(mox.IgnoreArg(), 'text1', 'bo')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <string1>fo</string1>
          <text1>go</text1>
          <text2>bo</text2>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyNodes(model, nodes[0], FOO_NAMES, lambda x: x + 'o',
                       # Swap text1 and text2.
                       name_map={'text1': 'text2', 'text2': 'text1'})
    self.assertEquals(model.string1, 'foo')
    self.assertEquals(model.text2, 'goo')
    self.assertEquals(model.text1, 'boo')

  def testCopyNodes_withConversionError(self):
    # Values are logged before conversion.
    xml_util.logger.debug(mox.IgnoreArg(), 'integer1', '123')
    xml_util.logger.debug(mox.IgnoreArg(), 'integer2', 'xyz')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <integer1>123</integer1>
          <integer2>xyz</integer2>
        </foo>""", 'foo')
    model = FooModel()
    self.assertReturnsErrorWithRegexpMatch(
        xml_util.CopyNodeError, 'Error copying .integer2.',
        xml_util.CopyNodes, model, nodes[0], FOO_NAMES, int)
    # Properties before the error will be set.
    self.assertEquals(model.integer1, 123)

  def testCopyNodes_withInvalidType(self):
    # Values are logged before being assigned to the property.
    xml_util.logger.debug(mox.IgnoreArg(), 'integer1', '123')
    xml_util.logger.debug(mox.IgnoreArg(), 'text1', '456')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <integer1>123</integer1>
          <text1>456</text1>
        </foo>""", 'foo')
    model = FooModel()
    self.assertReturnsErrorWithRegexpMatch(
        xml_util.CopyNodeError, 'Error copying .text1.',
        xml_util.CopyNodes, model, nodes[0], FOO_NAMES, int)
    # Properties before the error will be set.
    self.assertEquals(model.integer1, 123)

  def testCopyNodes_withInvalidName(self):
    # It seems that db.Model will accept any attribute via setattr, even ones
    # not defined in the FooModel class.  Go figure.
    xml_util.logger.debug(mox.IgnoreArg(), 'text2', 'foo')
    xml_util.logger.debug(mox.IgnoreArg(), 'blargh', 'bar')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <text2>foo</text2>
          <blargh>bar</blargh>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyNodes(model, nodes[0], ['text2', 'blargh'], str)
    self.assertEquals(model.text2, 'foo')
    self.assertEquals(model.blargh, 'bar')

  def testCopyNodes_toCapAlert(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'identifier', '123')
    xml_util.logger.debug(mox.IgnoreArg(), 'sender', 'foo@bar')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <alert>
          <identifier>123</identifier>
          <sender>foo@bar</sender>
        </alert>""", 'alert')
    alert = caplib.Alert()
    xml_util.CopyNodes(alert, nodes[0], ['identifier', 'sender'], str)
    self.assertEquals(alert.identifier, '123')
    self.assertEquals(alert.sender, 'foo@bar')


class CopyNodeListsTest(XmlUtilTestBase):
  """Tests for the CopyNodeLists method."""

  def testCopyNodeLists_withNoChildNodes(self):
    self.mox.ReplayAll()
    nodes = ParseXml('<?xml version="1.0" ?><foo/>', 'foo')
    model = FooModel()
    original_dict = db_util.ModelAsDict(FooModel, model)
    xml_util.CopyNodeLists(model, nodes[0], FOO_NAMES,
                       lambda x: self.assertNotEquals(x, x))
    self.assertDictEqual(db_util.ModelAsDict(FooModel, model), original_dict)

  def testCopyNodeLists_withEmptyText(self):
    self.mox.ReplayAll()
    nodes = ParseXml(
        '<?xml version="1.0" ?><foo><text_list1/><text_list2/></foo>', 'foo')
    model = FooModel()
    original_dict = db_util.ModelAsDict(FooModel, model)
    xml_util.CopyNodeLists(model, nodes[0], FOO_NAMES,
                       lambda x: self.assertNotEquals(x, x))
    self.assertDictEqual(db_util.ModelAsDict(FooModel, model), original_dict)

  def testCopyNodeLists_DeadlineExceededError(self):
    self.mox.StubOutWithMock(xml_util, 'GetText')
    xml_util.GetText(mox.IgnoreArg()).AndRaise(DeadlineExceededError)
    self.mox.ReplayAll()

    nodes = ParseXml(
        '<?xml version="1.0" ?><foo><text_list1/><text_list2/></foo>', 'foo')
    model = FooModel()
    self.assertRaises(DeadlineExceededError,
                      xml_util.CopyNodeLists, model, nodes[0], FOO_NAMES,
                      lambda x: self.assertNotEquals(x, x))

  def testCopyNodeLists_withNominalData(self):
    # Logged values are unconverted.
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list1', 'go1')
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list1', 'go2')
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list2', 'bo1')
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list2', 'bo2')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <text_list1>go1</text_list1>
          <text_list1>go2</text_list1>
          <text_list2>bo1</text_list2>
          <text_list2>bo2</text_list2>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyNodeLists(model, nodes[0], FOO_NAMES, lambda x: x + 'o')
    self.assertListEqual(model.text_list1, ['go1o', 'go2o'])
    self.assertListEqual(model.text_list2, ['bo1o', 'bo2o'])

  def testCopyNodeLists_withNameMap(self):
    # If it's not in the name map, the name stays the same.
    xml_util.logger.debug(mox.IgnoreArg(), 'string_list1', 'fo1')
    xml_util.logger.debug(mox.IgnoreArg(), 'string_list1', 'fo2')
    # Logged values are post-name-mapping.
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list2', 'go1')
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list2', 'go2')
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list1', 'bo1')
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list1', 'bo2')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <string_list1>fo1</string_list1>
          <string_list1>fo2</string_list1>
          <text_list1>go1</text_list1>
          <text_list1>go2</text_list1>
          <text_list2>bo1</text_list2>
          <text_list2>bo2</text_list2>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyNodeLists(model, nodes[0], FOO_NAMES, lambda x: x + 'o',
                           # Swap text_list and text_list2.
                           name_map={'text_list1': 'text_list2',
                                     'text_list2': 'text_list1'})
    self.assertListEqual(model.string_list1, ['fo1o', 'fo2o'])
    self.assertListEqual(model.text_list2, ['go1o', 'go2o'])
    self.assertListEqual(model.text_list1, ['bo1o', 'bo2o'])

  def testCopyNodeLists_withConversionError(self):
    # Values are logged before conversion.
    xml_util.logger.debug(mox.IgnoreArg(), 'integer_list1', '123')
    xml_util.logger.debug(mox.IgnoreArg(), 'integer_list1', 'xyz')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <integer_list1>123</integer_list1>
          <integer_list1>xyz</integer_list1>
        </foo>""", 'foo')
    model = FooModel()
    self.assertReturnsErrorWithRegexpMatch(
        xml_util.CopyNodeError, 'Error copying .integer_list1.',
        xml_util.CopyNodeLists, model, nodes[0], FOO_NAMES, int)
    # Properties before the error will be set.
    self.assertListEqual(model.integer_list1, [123])

  def testCopyNodeLists_withInvalidType(self):
    # List properties will accept invalid types, at least temporarily.
    xml_util.logger.debug(mox.IgnoreArg(), 'integer_list1', '123')
    xml_util.logger.debug(mox.IgnoreArg(), 'string_list1', '456')
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list1', '789')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <integer_list1>123</integer_list1>
          <string_list1>456</string_list1>
          <text_list1>789</text_list1>
        </foo>""", 'foo')
    model = FooModel()
    xml_util.CopyNodeLists(model, nodes[0], FOO_NAMES, int)
    self.assertEquals(model.integer_list1, [123])
    self.assertEquals(model.string_list1, [456])
    self.assertEquals(model.text_list1, [789])

  def testCopyNodeLists_withInvalidName(self):
    xml_util.logger.debug(mox.IgnoreArg(), 'text_list2', 'foo')
    xml_util.logger.debug(mox.IgnoreArg(), 'blargh', 'bar')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <foo>
          <text_list2>foo</text_list2>
          <blargh>bar</blargh>
        </foo>""", 'foo')
    model = FooModel()
    self.assertReturnsErrorWithRegexpMatch(
        xml_util.CopyNodeError, 'Error copying .blargh. .* AttributeError',
        xml_util.CopyNodeLists, model, nodes[0], ['text_list2', 'blargh'], str)
    self.assertEquals(model.text_list2, ['foo'])

  def testCopyNodeLists_toCapAlert(self):
    # Values are logged before conversion.
    xml_util.logger.debug(mox.IgnoreArg(), 'codes', '123')
    xml_util.logger.debug(mox.IgnoreArg(), 'codes', '456')
    self.mox.ReplayAll()

    nodes = ParseXml(
        """<?xml version="1.0" ?>
        <alert>
          <codes>123</codes>
          <codes>456</codes>
        </alert>""", 'alert')
    alert = caplib.Alert()
    xml_util.CopyNodeLists(alert, nodes[0], ['codes'], str)
    self.assertListEqual(list(alert.codes), ['123', '456'])


def main(unused_argv):
  googletest.main()


if __name__ == '__main__':
  app.run()
