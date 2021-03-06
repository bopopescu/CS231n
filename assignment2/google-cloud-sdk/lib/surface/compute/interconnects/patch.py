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
"""Command for creating interconnects."""


from googlecloudsdk.api_lib.compute import base_classes
from googlecloudsdk.api_lib.compute.interconnects import client
from googlecloudsdk.calliope import base
from googlecloudsdk.command_lib.compute.interconnects import flags
from googlecloudsdk.command_lib.util import labels_util


def _ArgsCommon(cls, parser, support_labels=False):
  """Shared arguments for patch commands."""
  cls.INTERCONNECT_ARG = flags.InterconnectArgument()
  cls.INTERCONNECT_ARG.AddArgument(parser, operation_type='patch')

  parser.add_argument(
      '--description',
      help='An optional, textual description for the interconnect.')
  flags.AddAdminEnabledForPatch(parser)
  flags.AddNocContactEmail(parser)
  flags.AddRequestedLinkCountForPatch(parser)
  if support_labels:
    labels_util.AddUpdateLabelsFlags(parser)


@base.ReleaseTracks(base.ReleaseTrack.BETA, base.ReleaseTrack.GA)
class Patch(base.UpdateCommand):
  """Patch a Google Compute Engine interconnect.

  *{command}* is used to patch interconnects. An interconnect represents a
  single specific connection between Google and the customer
  """
  INTERCONNECT_ARG = None

  @classmethod
  def Args(cls, parser):
    _ArgsCommon(cls, parser)

  def Collection(self):
    return 'compute.interconnects'

  def _DoRun(self, args, support_labels=False):
    holder = base_classes.ComputeApiHolder(self.ReleaseTrack())
    ref = self.INTERCONNECT_ARG.ResolveAsResource(args, holder.resources)
    interconnect = client.Interconnect(ref, compute_client=holder.client)

    labels = None
    label_fingerprint = None
    if support_labels:
      labels_diff = labels_util.Diff.FromUpdateArgs(args)
      if labels_diff.MayHaveUpdates():
        old_interconnect = interconnect.Describe()
        labels = labels_diff.Apply(
            holder.client.messages.Interconnect.LabelsValue,
            old_interconnect.labels).GetOrNone()
        if labels is not None:
          label_fingerprint = old_interconnect.labelFingerprint

    return interconnect.Patch(
        description=args.description,
        interconnect_type=None,
        requested_link_count=args.requested_link_count,
        link_type=None,
        admin_enabled=args.admin_enabled,
        noc_contact_email=args.noc_contact_email,
        location=None,
        labels=labels,
        label_fingerprint=label_fingerprint
    )

  def Run(self, args):
    self._DoRun(args)


@base.ReleaseTracks(base.ReleaseTrack.ALPHA)
class PatchLabels(Patch):
  """Patch a Google Compute Engine interconnect.

  *{command}* is used to patch interconnects. An interconnect represents a
  single specific connection between Google and the customer
  """

  @classmethod
  def Args(cls, parser):
    _ArgsCommon(cls, parser, support_labels=True)

  def Run(self, args):
    self._DoRun(args, support_labels=True)
