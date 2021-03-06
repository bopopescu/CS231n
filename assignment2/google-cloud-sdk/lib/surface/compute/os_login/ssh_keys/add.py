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

"""Implements the command to add an SSH public key to the OS Login profile."""

from googlecloudsdk.api_lib.oslogin import client
from googlecloudsdk.calliope import base
from googlecloudsdk.command_lib.oslogin import flags
from googlecloudsdk.command_lib.oslogin import oslogin_utils
from googlecloudsdk.core import properties


class Add(base.Command):
  """SSH into a virtual machine instance."""

  def __init__(self, *args, **kwargs):
    super(Add, self).__init__(*args, **kwargs)

  @staticmethod
  def Args(parser):
    """Set up arguments for this command.

    Args:
      parser: An argparse.ArgumentParser.
    """
    flags.AddKeyFlags(parser, 'add to')
    flags.AddTtlFlag(parser)

  def Run(self, args):
    """See ssh_utils.BaseSSHCLICommand.Run."""
    key = flags.GetKeyFromArgs(args)
    oslogin_client = client.OsloginClient(self.ReleaseTrack())
    user_email = properties.VALUES.core.account.Get()

    expiry = oslogin_utils.ConvertTtlArgToExpiry(args.ttl)

    return oslogin_client.ImportSshPublicKey(user_email, key,
                                             expiration_time=expiry)


Add.detailed_help = {
    'brief': 'Add an SSH public key to an OS Login profile.',
    'DESCRIPTION': """\
      *{command}* will take either a string containing an SSH public
      key or a filename for an SSH public key and will add that key to the
      user's OS Login profile.
    """
}

