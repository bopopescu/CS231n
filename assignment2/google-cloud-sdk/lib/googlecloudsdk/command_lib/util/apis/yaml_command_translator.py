# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A yaml to calliope command translator.

Calliope allows you to register a hook that converts a yaml command spec into
a calliope command class. The Translator class in this module implements that
interface and provides generators for a yaml command spec. The schema for the
spec can be found in yaml_command_schema.yaml.
"""

from apitools.base.protorpclite import messages as apitools_messages
from googlecloudsdk.api_lib.util import waiter
from googlecloudsdk.calliope import base
from googlecloudsdk.calliope import command_loading
from googlecloudsdk.command_lib.util.apis import arg_marshalling
from googlecloudsdk.command_lib.util.apis import registry
from googlecloudsdk.command_lib.util.apis import yaml_command_schema
from googlecloudsdk.core import exceptions
from googlecloudsdk.core import log
from googlecloudsdk.core import resources
from googlecloudsdk.core.console import console_io


class Translator(command_loading.YamlCommandTranslator):
  """Class that implements the calliope translator interface."""

  def Translate(self, path, command_data):
    spec = yaml_command_schema.CommandData(path[-1], command_data)
    c = CommandBuilder(spec)
    return c.Generate()


class CommandBuilder(object):
  """Generates calliope commands based on the yaml spec."""

  IGNORED_FLAGS = {'project'}

  def __init__(self, spec):
    self.spec = spec
    self.method = registry.GetMethod(
        self.spec.request.collection, self.spec.request.method,
        self.spec.request.api_version)
    resource_arg = self.spec.arguments.resource
    self.arg_generator = arg_marshalling.DeclarativeArgumentGenerator(
        self.method,
        self.spec.arguments.params,
        resource_arg)
    self.resource_type = resource_arg.name if resource_arg else None

  def Generate(self):
    """Generates a calliope command from the yaml spec.

    Raises:
      ValueError: If we don't know how to generate the given command type (this
        is not actually possible right now due to the enum).

    Returns:
      calliope.base.Command, The command that implements the spec.
    """
    if self.spec.command_type == yaml_command_schema.CommandType.DESCRIBE:
      command = self._GenerateDescribeCommand()
    elif self.spec.command_type == yaml_command_schema.CommandType.LIST:
      command = self._GenerateListCommand()
    elif self.spec.command_type == yaml_command_schema.CommandType.DELETE:
      command = self._GenerateDeleteCommand()
    elif self.spec.command_type == yaml_command_schema.CommandType.CREATE:
      command = self._GenerateCreateCommand()
    elif self.spec.command_type == yaml_command_schema.CommandType.WAIT:
      command = self._GenerateWaitCommand()
    elif self.spec.command_type == yaml_command_schema.CommandType.GENERIC:
      command = self._GenerateGenericCommand()
    else:
      raise ValueError('Unknown command type')
    self._ConfigureGlobalAttributes(command)
    return command

  def _GenerateDescribeCommand(self):
    """Generates a Describe command.

    A describe command has a single resource argument and an API method to call
    to get the resource. The result is returned using the default output format.

    Returns:
      calliope.base.Command, The command that implements the spec.
    """

    # pylint: disable=no-self-argument, The class closure throws off the linter
    # a bit. We want to use the generator class, not the class being generated.
    # pylint: disable=protected-access, The linter gets confused about 'self'
    # and thinks we are accessing something protected.
    class Command(base.DescribeCommand):

      @staticmethod
      def Args(parser):
        self._CommonArgs(parser)

      def Run(self_, args):
        unused_ref, response = self._CommonRun(args)
        return self._HandleResponse(response)

    return Command

  def _GenerateListCommand(self):
    """Generates a List command.

    A list command operates on a single resource and has flags for the parent
    collection of that resource. Because it extends the calliope base List
    command, it gets flags for things like limit, filter, and page size. A
    list command should register a table output format to display the result.
    If arguments.resource.response_id_field is specified, a --uri flag will also
    be enabled.

    Returns:
      calliope.base.Command, The command that implements the spec.
    """

    # pylint: disable=no-self-argument, The class closure throws off the linter
    # a bit. We want to use the generator class, not the class being generated.
    # pylint: disable=protected-access, The linter gets confused about 'self'
    # and thinks we are accessing something protected.
    class Command(base.ListCommand):

      @staticmethod
      def Args(parser):
        self._CommonArgs(parser)
        # Remove the URI flag if we don't know how to generate URIs for this
        # resource.
        if not self.spec.response.id_field:
          base.URI_FLAG.RemoveFromParser(parser)

      def Run(self_, args):
        self._RegisterURIFunc(args)
        unused_ref, response = self._CommonRun(args)
        return self._HandleResponse(response)

    return Command

  def _GenerateDeleteCommand(self):
    """Generates a Delete command.

    A delete command has a single resource argument and an API to call to
    perform the delete. If the async section is given in the spec, an --async
    flag is added and polling is automatically done on the response. For APIs
    that adhere to standards, no further configuration is necessary. If the API
    uses custom operations, you may need to provide extra configuration to
    describe how to poll the operation.

    Returns:
      calliope.base.Command, The command that implements the spec.
    """

    # pylint: disable=no-self-argument, The class closure throws off the linter
    # a bit. We want to use the generator class, not the class being generated.
    # pylint: disable=protected-access, The linter gets confused about 'self'
    # and thinks we are accessing something protected.
    class Command(base.DeleteCommand):

      @staticmethod
      def Args(parser):
        self._CommonArgs(parser)
        if self.spec.async:
          base.ASYNC_FLAG.AddToParser(parser)

      def Run(self_, args):
        ref, response = self._CommonRun(args)
        if self.spec.async:
          response = self._HandleAsync(
              args, ref, response,
              request_string='Delete request issued for: [{{{}}}]'
              .format(yaml_command_schema.NAME_FORMAT_KEY),
              extract_resource_result=False)
          if args.async:
            return self._HandleResponse(response)

        response = self._HandleResponse(response)
        log.DeletedResource(ref.Name(), kind=self.resource_type)
        return response

    return Command

  def _GenerateCreateCommand(self):
    """Generates a Create command.

    A create command has a single resource argument and an API to call to
    perform the creation. If the async section is given in the spec, an --async
    flag is added and polling is automatically done on the response. For APIs
    that adhere to standards, no further configuration is necessary. If the API
    uses custom operations, you may need to provide extra configuration to
    describe how to poll the operation.

    Returns:
      calliope.base.Command, The command that implements the spec.
    """

    # pylint: disable=no-self-argument, The class closure throws off the linter
    # a bit. We want to use the generator class, not the class being generated.
    # pylint: disable=protected-access, The linter gets confused about 'self'
    # and thinks we are accessing something protected.
    class Command(base.CreateCommand):

      @staticmethod
      def Args(parser):
        self._CommonArgs(parser)
        if self.spec.async:
          base.ASYNC_FLAG.AddToParser(parser)

      def Run(self_, args):
        ref, response = self._CommonRun(args)
        if self.spec.async:
          response = self._HandleAsync(
              args, ref, response,
              request_string='Create request issued for: [{{{}}}]'
              .format(yaml_command_schema.NAME_FORMAT_KEY))
          if args.async:
            return self._HandleResponse(response)

        response = self._HandleResponse(response)
        log.CreatedResource(ref.Name(), kind=self.resource_type)
        return response

    return Command

  def _GenerateWaitCommand(self):
    """Generates a wait command for polling operations.

    A wait command takes an operation reference and polls the status until it
    is finished or errors out. This follows the exact same spec as in other
    async commands except the primary operation (create, delete, etc) has
    already been done. For APIs that adhere to standards, no further async
    configuration is necessary. If the API uses custom operations, you may need
    to provide extra configuration to describe how to poll the operation.

    Returns:
      calliope.base.Command, The command that implements the spec.
    """

    # pylint: disable=no-self-argument, The class closure throws off the linter
    # a bit. We want to use the generator class, not the class being generated.
    # pylint: disable=protected-access, The linter gets confused about 'self'
    # and thinks we are accessing something protected.
    class Command(base.Command):

      @staticmethod
      def Args(parser):
        self._CommonArgs(parser)

      def Run(self_, args):
        ref = self.arg_generator.GetRequestResourceRef(args)
        response = self._WaitForOperation(
            ref, resource_ref=None, extract_resource_result=False)
        response = self._HandleResponse(response)
        return response

    return Command

  def _GenerateGenericCommand(self):
    """Generates a generic command.

    A generic command has a resource argument, additional fields, and calls an
    API method. It supports async if the async configuration is given. Any
    fields is message_params will be generated as arguments and inserted into
    the request message.

    Returns:
      calliope.base.Command, The command that implements the spec.
    """

    # pylint: disable=no-self-argument, The class closure throws off the linter
    # a bit. We want to use the generator class, not the class being generated.
    # pylint: disable=protected-access, The linter gets confused about 'self'
    # and thinks we are accessing something protected.
    class Command(base.Command):

      @staticmethod
      def Args(parser):
        self._CommonArgs(parser)
        if self.spec.async:
          base.ASYNC_FLAG.AddToParser(parser)

      def Run(self_, args):
        ref, response = self._CommonRun(args)
        if self.spec.async:
          request_string = None
          if ref:
            request_string = 'Request issued for: [{{{}}}]'.format(
                yaml_command_schema.NAME_FORMAT_KEY)
          response = self._HandleAsync(
              args, ref, response, request_string=request_string)
        return self._HandleResponse(response)

    return Command

  def _CommonArgs(self, parser):
    """Performs argument actions common to all commands.

    Adds all generated arguments to the parser
    Sets the command output format if specified

    Args:
      parser: The argparse parser.
    """
    args = self.arg_generator.GenerateArgs()
    for arg in args:
      arg.AddToParser(parser)
    if self.spec.arguments.additional_arguments_hook:
      for arg in self.spec.arguments.additional_arguments_hook():
        arg.AddToParser(parser)
    if self.spec.output.format:
      parser.display_info.AddFormat(self.spec.output.format)

  def _CommonRun(self, args):
    """Performs run actions common to all commands.

    Parses the resource argument into a resource reference
    Prompts the user to continue (if applicable)
    Calls the API method with the request generated from the parsed arguments

    Args:
      args: The argparse parser.

    Returns:
      (resources.Resource, response), A tuple of the parsed resource reference
      and the API response from the method call.
    """
    ref = self.arg_generator.GetRequestResourceRef(args)
    if self.spec.input.confirmation_prompt:
      console_io.PromptContinue(
          self._Format(self.spec.input.confirmation_prompt, ref),
          throw_if_unattended=True, cancel_on_no=True)

    if self.spec.request.issue_request_hook:
      # Making the request is overridden, just call into the custom code.
      return ref, self.spec.request.issue_request_hook(ref, args)

    if self.spec.request.create_request_hook:
      # We are going to make the request, but there is custom code to create it.
      request = self.spec.request.create_request_hook(ref, args)
    else:
      request = self.arg_generator.CreateRequest(
          args, self.spec.request.static_fields,
          self.spec.request.resource_method_params)
      for hook in self.spec.request.modify_request_hooks:
        request = hook(ref, args, request)

    response = self.method.Call(request,
                                limit=self.arg_generator.Limit(args),
                                page_size=self.arg_generator.PageSize(args))
    return ref, response

  def _HandleAsync(self, args, resource_ref, operation,
                   request_string, extract_resource_result=True):
    """Handles polling for operations if the async flag is provided.

    Args:
      args: argparse.Namespace, The parsed args.
      resource_ref: resources.Resource, The resource reference for the resource
        being operated on (not the operation itself)
      operation: The operation message response.
      request_string: The format string to print indicating a request has been
        issued for the resource. If None, nothing is printed.
      extract_resource_result: bool, True to return the original resource as
        the result or False to just return the operation response when it is
        done. You would set this to False for things like Delete where the
        resource no longer exists when the operation is done.

    Returns:
      The response (either the operation or the original resource).
    """
    operation_ref = resources.REGISTRY.Parse(
        getattr(operation, self.spec.async.response_name_field),
        collection=self.spec.async.collection)
    if request_string:
      log.status.Print(self._Format(request_string, resource_ref))
    if args.async:
      log.status.Print(self._Format(
          'Check operation [{{{}}}] for status.'
          .format(yaml_command_schema.NAME_FORMAT_KEY), operation_ref))
      return operation

    return self._WaitForOperation(
        operation_ref, resource_ref, extract_resource_result)

  def _WaitForOperation(self, operation_ref, resource_ref,
                        extract_resource_result):
    poller = AsyncOperationPoller(
        self.spec, resource_ref if extract_resource_result else None)
    progress_string = self._Format(
        'Waiting for operation [{{{}}}] to complete'.format(
            yaml_command_schema.NAME_FORMAT_KEY),
        operation_ref)
    return waiter.WaitFor(
        poller, operation_ref, self._Format(progress_string, resource_ref))

  def _HandleResponse(self, response):
    """Process the API response.

    Args:
      response: The apitools message object containing the API response.

    Raises:
      core.exceptions.Error: If an error was detected and extracted from the
        response.

    Returns:
      A possibly modified response.
    """
    if self.spec.response.error:
      error = self._FindPopulatedAttribute(
          response, self.spec.response.error.field.split('.'))
      if error:
        messages = []
        if self.spec.response.error.code:
          messages.append('Code: [{}]'.format(
              _GetAttribute(error, self.spec.response.error.code)))
        if self.spec.response.error.message:
          messages.append('Message: [{}]'.format(
              _GetAttribute(error, self.spec.response.error.message)))
        if messages:
          raise exceptions.Error(' '.join(messages))
        raise exceptions.Error(str(error))
    if self.spec.response.result_attribute:
      response = _GetAttribute(response, self.spec.response.result_attribute)
    return response

  def _FindPopulatedAttribute(self, obj, attributes):
    """Searches the given object for an attribute that is non-None.

    This digs into the object search for the given attributes. If any attribute
    along the way is a list, it will search for sub-attributes in each item
    of that list. The first match is returned.

    Args:
      obj: The object to search
      attributes: [str], A sequence of attributes to use to dig into the
        resource.

    Returns:
      The first matching instance of the attribute that is non-None, or None
      if one could nto be found.
    """
    if not attributes:
      return obj
    attr = attributes[0]
    try:
      obj = getattr(obj, attr)
    except AttributeError:
      return None
    if isinstance(obj, list):
      for x in obj:
        obj = self._FindPopulatedAttribute(x, attributes[1:])
        if obj:
          return obj
    return self._FindPopulatedAttribute(obj, attributes[1:])

  def _Format(self, format_string, resource_ref):
    """Formats a string with all the attributes of the given resource ref.

    Args:
      format_string: str, The format string.
      resource_ref: resources.Resource, The resource reference to extract
        attributes from.

    Returns:
      str, The formatted string.
    """
    if resource_ref:
      d = resource_ref.AsDict()
      d[yaml_command_schema.NAME_FORMAT_KEY] = resource_ref.Name()
      d[yaml_command_schema.REL_NAME_FORMAT_KEY] = resource_ref.RelativeName()
    else:
      d = {}
    d[yaml_command_schema.RESOURCE_TYPE_FORMAT_KEY] = self.resource_type
    return format_string.format(**d)

  def _RegisterURIFunc(self, args):
    """Generates and registers a function to create a URI from a resource.

    Args:
      args: The argparse namespace.

    Returns:
      f(resource) -> str, A function that converts the given resource payload
      into a URI.
    """
    def URIFunc(resource):
      id_value = getattr(
          resource, self.spec.response.id_field)
      ref = self.arg_generator.GetResponseResourceRef(id_value, args)
      return ref.SelfLink()
    args.GetDisplayInfo().AddUriFunc(URIFunc)

  def _ConfigureGlobalAttributes(self, command):
    """Configures top level attributes of the generated command.

    Args:
      command: The command being generated.
    """
    if self.spec.is_hidden:
      command = base.Hidden(command)
    if self.spec.release_tracks:
      command = base.ReleaseTracks(*self.spec.release_tracks)(command)
    command.detailed_help = self.spec.help_text
    command.detailed_help['API REFERENCE'] = (
        'This command uses the *{}/{}* API. The full documentation for this '
        'API can be found at: {}'.format(
            self.method.collection.api_name, self.method.collection.api_version,
            self.method.collection.docs_url))


class AsyncOperationPoller(waiter.OperationPoller):
  """An implementation of a operation poller."""

  def __init__(self, spec, resource_ref):
    """Creates the poller.

    Args:
      spec: yaml_command_schema.CommandData, the spec for the command being
        generated.
      resource_ref: resources.Resource, The resource reference for the resource
        being operated on (not the operation itself). If None, the operation
        will just be returned when it is done instead of getting the resulting
        resource.
    """
    self.spec = spec
    self.resource_ref = resource_ref
    if not self.spec.async.extract_resource_result:
      self.resource_ref = None
    self.method = registry.GetMethod(
        spec.async.collection, spec.async.method,
        api_version=spec.async.api_version or spec.request.api_version)

  def IsDone(self, operation):
    """Overrides."""
    result = getattr(operation, self.spec.async.state.field)
    if isinstance(result, apitools_messages.Enum):
      result = result.name
    if (result in self.spec.async.state.success_values or
        result in self.spec.async.state.error_values):
      # We found a value that means it is done.
      error = getattr(operation, self.spec.async.error.field)
      if not error and result in self.spec.async.state.error_values:
        error = 'The operation failed.'
      # If we succeeded but there is an error, or if an error was detected.
      if error:
        raise waiter.OperationError(error)
      return True

    return False

  def Poll(self, operation_ref):
    """Overrides.

    Args:
      operation_ref: googlecloudsdk.core.resources.Resource.

    Returns:
      fetched operation message.
    """
    request_type = self.method.GetRequestType()
    relative_name = operation_ref.RelativeName()
    fields = {
        f.name: getattr(
            operation_ref,
            self.spec.async.operation_get_method_params.get(f.name, f.name),
            relative_name)
        for f in request_type.all_fields()}
    return self.method.Call(request_type(**fields))

  def GetResult(self, operation):
    """Overrides.

    Args:
      operation: api_name_messages.Operation.

    Returns:
      result of result_service.Get request.
    """
    result = operation
    if self.resource_ref:
      method = self._ResourceGetMethod()
      result = method.Call(method.GetRequestType()(
          **self.resource_ref.AsDict()))
    return _GetAttribute(result, self.spec.async.result_attribute)

  def _ResourceGetMethod(self):
    return registry.GetMethod(
        self.spec.request.collection, self.spec.async.resource_get_method,
        api_version=self.spec.request.api_version)


def _GetAttribute(obj, attr_path):
  """Gets attributes and sub-attributes out of an object.

  Args:
    obj: The object to extract the attributes from.
    attr_path: str, The dotted path of attributes to extract.

  Raises:
    AttributeError: If the attribute doesn't exist on the object.

  Returns:
    The desired attribute or None if any of the parent attributes were None.
  """
  if attr_path:
    for attr in attr_path.split('.'):
      try:
        if obj is None:
          return None
        obj = getattr(obj, attr)
      except AttributeError:
        raise AttributeError(
            'Attribute path [{}] not found on type [{}]'.format(attr_path,
                                                                type(obj)))
  return obj
