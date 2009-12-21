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

"""Flexible web-based query capability for Datastore.

An application would instantiate a Schema object in order to define how the
Datastore will be queryable.

Web requests can then be transformed into Query objects via
Schema.QueryFromRequest.  Each request argument is considered to be a
predicate of the form model.attribute[.operator]=value.  The default operator
is equality (=).

Query objects can produce GQL fragments and parameter dict's that are
compatible with the Datastore GqlQuery API.  They can also be used to filter
model instances that are already materialized.  This is useful if a predicate
cannot be evaluated by the Datastore due to restrictions on the complexity of
the query predicates.
"""

__author__ = 'Matthew.H.Frantz@gmail.com (Matt Frantz)'

try:
  from google3.pyglib import logging
except ImportError:
  import logging


class Schema(object):
  """Defines the queryable components of a Datastore schema."""

  def __init__(self, models, default_model):
    """Initializes a Schema object.

    Args:
      models: Dict of Model info
      default_model: If no model is specified in the CGI argument, this model
          name is used (str).
    """
    self.__models = models
    self.__default_model = default_model

  def QueryFromRequest(self, request):
    """Constructs a Query representing the request.

    Request arguments are treated as specifications of query predicates that
    are to be intersected (AND'ed).

    Args:
      request: webapp.Request object
      schema: Schema object

    Returns:
      (query, unknown_arguments)
      query: Query object
      unknown_arguments: set of unknown arguments (str)
    """
    predicates = []
    unknown_arguments = set()
    for argument in request.arguments():
      # Parse the argument name.
      model, attribute, operator_name = _ParseArgument(argument)
      if not model:
        model = self.__default_model
      if not operator_name:
        operator_name = '='
      if model not in self.__models:
        logging.error('Unknown model %r', model)
        unknown_arguments.add(argument)
        continue
      attributes = self.__models[model]
      if attribute not in attributes:
        logging.error('Unknown attribute %r for model %r', attribute, model)
        unknown_arguments.add(argument)
        continue
      operators = attributes[attribute]
      if operator_name not in operators:
        logging.error('Unknown operator %r for attribute %r',
                      operator_name, attribute)
        unknown_arguments.add(argument)
        continue
      operator = operators[operator_name]
      # See what the argument values are.
      values = request.get_all(argument)
      # Form the predicate.
      predicates.append(operator.MakePredicate(model, attribute, values))
    return Query(predicates), unknown_arguments

  def Help(self):
    """Makes a data structure that can be used in a Django template argument.

    Returns:
      List of ModelHelp objects
    """
    help = []
    for model_name, attributes in self.__models.iteritems():
      attribute_help = []
      for attribute_name, operators in attributes.iteritems():
        attribute_help.append({'name': attribute_name,
                               'operators': operators})
      help.append({'name': model_name,
                   'attributes': attribute_help})
    return help


class BinaryOperator(object):
  """Represents and implements a binary operator."""

  def __init__(self, gql, executor):
    self.gql = gql
    self.__executor = executor

  def __call__(self, x, y):
    return self.__executor(x, y)

  def __str__(self):
    return self.gql

  def MakePredicate(self, model, attribute, argument):
    """Constructs a predicate.

    Args:
      model: Model name (str)
      attribute: Attribute name (str)
      argument: CGI argument (list of str)
    """
    return SimpleComparisonPredicate(model, attribute, argument, self)


class EqualityOperator(BinaryOperator):
  """Represents and implements an equality operator.

  Equality operators include strict equality (=) and set membership (IN).
  They are logically interchangeable.  This class includes code that optimizes
  the equality expression depending on the cardinality of the argument set.

  Attributes:
    equals_operator: Equality operator where argument is a single value.
    in_operator: Membership test operator where argument is set of values.
  """

  def MakePredicate(self, model, attribute, argument):
    """Constructs a predicate.

    Args:
      model: Model name (str)
      attribute: Attribute name (str)
      argument: CGI argument (list of str)
    """
    operator = self
    # If we want to compare with a single value, use the corresponding EQUALS.
    if len(argument) == 1:
      operator = self.equals_operator
      argument = argument[0]
    else:
      # If we have multiple values, use the corresponding IN.
      operator = self.in_operator

    if operator is self:
      return super(EqualityOperator, self).MakePredicate(
          model, attribute, argument)
    else:
      return operator.MakePredicate(model, attribute, argument)

  @staticmethod
  def Tie(equals_operator, in_operator):
    """Associates logically equivalent equality operators.

    Args:
      equals_operator: Equality operator where argument is a single value.
      in_operator: Membership test operator where argument is set of values.

    Postconditions:
      Both operators' attributes, equals_operator and in_operator, are set.
    """
    for operator in (equals_operator, in_operator):
      operator.equals_operator = equals_operator
      operator.in_operator = in_operator


class Operators(object):
  """Enumeration of query operators."""

  SCALAR_EQUALS = EqualityOperator('=', lambda x, y: x == y)
  SCALAR_IN = EqualityOperator('IN', lambda x, y: x in y)
  EqualityOperator.Tie(SCALAR_EQUALS, SCALAR_IN)

  # TODO(Matt Frantz): Add operators for ranges (timestamps) and geo.

  SCALAR_ALL = dict([(x.gql, x) for x in [SCALAR_EQUALS, SCALAR_IN]])

  # TODO(Matt Frantz): Support ranges for datetime types.
  DATETIME_ALL = SCALAR_ALL

  # Operators on list properties, i.e. LHS is a list.  Equality is defined as
  # RHS equality of any of the LHS elements.
  LIST_EQUALS = EqualityOperator('=', lambda x, y: y in x)
  # Membership test is defined as LHS contains any members of RHS.
  LIST_IN = EqualityOperator('IN', lambda x, y: bool(set(y) - set(x)))
  EqualityOperator.Tie(LIST_EQUALS, LIST_IN)
  LIST_ALL = dict([(x.gql, x) for x in [LIST_EQUALS, LIST_IN]])

  # Operators on key/reference properties, i.e. LHS is a db.Model instance.
  KEY_EQUALS = EqualityOperator('=', lambda x, y: x.key() == y)
  KEY_IN = EqualityOperator('IN', lambda x, y: x.key() in y)
  EqualityOperator.Tie(KEY_EQUALS, KEY_IN)
  KEY_ALL = dict([(x.gql, x) for x in [KEY_EQUALS, KEY_IN]])


class Query(object):
  """Collection of Predicates that apply to a hierarchical Datastore query.

  The collection is interpreted as a single, separable predicate composed by
  intersecting the constituent predicates.

  Attributes:
    models: Set of models with a predicate.
  """

  def __init__(self, predicates):
    """Initializes a Query object.

    Args:
      predicates: List of Predicate objects

    Postconditions:
      Predicates are assigned names unique in this Query.
    """
    self.__predicates = predicates
    self.models = frozenset([x.model for x in predicates])
    for i, predicate in enumerate(predicates):
      predicate.gql_name = 'p%d' % i

  @property
  def predicates(self):
    """Returns a copy of the predicates.

    Returns:
      List of Predicate objects
    """
    return list(self.__predicates)

  def ApplyToGql(self, model_name):
    """Applies any predicates as filters.

    Args:
      model_name: Name of the db.Model being queried

    Returns:
      Tuple of (gql_list, gql_params) where:
      gql_list: GQL predicate list (list of str)
      gql_params: Name/value pairs for binding the query
    """
    logging.debug('Query %s ApplyToGql for model %s', self, model_name)
    gql_list = []
    gql_params = {}
    for predicate in self.__predicates:
      predicate.MaybeApplyToGql(model_name, gql_list, gql_params)
    logging.debug('Query %s ApplyToGql => %s WHERE %r <= %r', self, model_name,
                  ' AND '.join(gql_list), gql_params)
    return gql_list, gql_params

  def PermitsModel(self, model_name, model):
    """Applies any predicates to a model instance.

    Args:
      model_name: Name of the db.Model being queried
      model: db.Model object

    Returns:
      False, iff this query explicitly proscribes the model.
    """
    logging.debug('Query %s PermitsModel %s (%s)', self, model_name, model)
    for predicate in self.__predicates:
      if not predicate.PermitsModel(model_name, model):
        return False
    return True

  def __str__(self):
    return ' and '.join([str(x) for x in self.__predicates])


class Predicate(object):
  """A query predicate that applies to a specific Model class.

  Attributes:
    model: Model class name (str)
  """

  def __init__(self, model):
    """Initializes a Predicate object.

    Args:
      model: Model class name (str)
    """
    self.model = model

  def MaybeApplyToGql(self, model_name, gql_list, gql_params):
    """Maybe applies this predicate as a filter on the Datastore query.

    If this predicate references a Model that does not apply to this query,
    the query will not be changed.

    Args:
      model_name: Name of the db.Model being queried
      gql_list: GQL predicate list (list of str)
      gql_params: Name/value pairs for binding the query

    Postconditions:
      gql_list possibly modified with a filter based on this predicate.
      gql_params possibly extended with predicate names and values.
    """
    if self.model != model_name:
      return
    self._ApplyToGql(gql_list, gql_params)

  def PermitsModel(self, model_name, model):
    """Applies the predicate to an instance of a model.

    Args:
      model_name: Name of the db.Model being queried
      model: db.Model object

    Returns:
      False, iff this predicate explicitly rejects the model; True, if the
      predicate does not apply to the model type, or allows the model instance
      explicitly.
    """
    # If this predicate is for a different model type, it does not apply.
    if self.model != model_name:
      return True
    return self._PermitsModel(model)

  def _ApplyToQuery(self, gql_list):
    """Applies this predicate as a filter on the Datastore query.

    Preconditions:
      This predicate already verified to apply to the Model being queried.

    Args:
      gql_list: GQL predicate list (list of str)

    Postconditions:
      gql_list modified with a filter based on this predicate.
    """
    raise NotImplementedError()

  def _PermitsModel(self, model):
    """Applies this predicate to a model instance.

    Preconditions:
      This predicate already verified to apply to the Model being queried.

    Args:
      model: db.Model object

    Returns:
      True, if the predicate allows the model; False, if it rejects it.
    """
    raise NotImplementedError()

  def __str__(self):
    """Subclass must implement this for debugging.

    Returns:
      Human-readable representation of this predicate.
    """
    raise NotImplementedError()


class SimpleComparisonPredicate(Predicate):
  """A predicate of the form <attribute> OP <constant>.

  Attributes:
    model: Model name (str)
    attribute: Attribute name (str)
    constant: Value object appropriate for the specified attribute.
    operator: Operator object
  """

  def __init__(self, model, attribute, constant, operator):
    """Initializes a SimpleEqualityPredicate object.

    Args:
      model: Model name (str)
      attribute: Attribute name (str)
      constant: Value object appropriate for the specified attribute.
      operator: Operator object
    """
    super(SimpleComparisonPredicate, self).__init__(model)
    self.attribute = attribute
    self.operator = operator
    self.constant = constant
    self.gql_name = None

  def _ApplyToGql(self, gql_list, gql_params):
    """Applies this predicate as a filter on the Datastore query.

    Preconditions:
      This predicate already verified to apply to the Model being queried.

    Args:
      gql_list: GQL predicate list (list of str)
      gql_params: Name/value pairs for binding the query

    Postconditions:
      gql_list modified with a GQL predicate string based on this predicate.
      gql_params possibly extended with predicate names and values.
    """
    gql = '%s %s :%s' % (self.attribute, self.operator.gql, self.gql_name)
    logging.debug('Predicate %s applied as GQL %r', self, gql)
    gql_list.append(gql)
    gql_params[self.gql_name] = self.constant

  def _PermitsModel(self, model):
    """Applies this predicate to a model instance.

    If the model does not have the attribute referenced by this predicate, it
    is assumed to be permitted.

    Args:
      model: db.Model object

    Returns:
      True, if the predicate allows the model; False, if it rejects it.
    """
    if hasattr(model, self.attribute):
      is_permitted = self.operator(getattr(model, self.attribute),
                                   self.constant)
      logging.debug('Predicate %s permits model? %s', self, is_permitted)
    else:
      is_permitted = True

    return is_permitted

  def __str__(self):
    """Human-readable representation of this predicate.

    Returns:
      str
    """
    return '%s.%s %s %r' % (
        self.model, self.attribute, self.operator, self.constant)


def _ParseArgument(argument):
  """Parses a CGI argument name.

  Args:
    argument: CGI argument name of the form [model.]attribute[.operator]
        (str or unicode)

  Returns:
    model (str), attribute (str), operator name (str)
  """
  tokens = str(argument).split('.', 2)
  if len(tokens) == 1:
    # If only one token, assume it is the attribute.
    return None, tokens[0], None
  elif len(tokens) == 2:
    # No operator specified.
    return tokens + [None]
  else:
    return tokens
