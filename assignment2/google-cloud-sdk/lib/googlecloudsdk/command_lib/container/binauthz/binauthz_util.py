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
"""Utilities for Binary Authorization commands."""

import base64
import md5
import urlparse

from containerregistry.client import docker_name  # pytype: disable=import-error
from googlecloudsdk.core import resources
from googlecloudsdk.core.exceptions import Error


class BadImageUrlError(Error):
  """Raised when a container image URL cannot be parsed successfully."""


def CreateProviderRefFromProjectRef(project_ref):
  """Given a project ref, create a Container Analysis `providers` ref."""
  provider_name = project_ref.Name()
  return resources.REGISTRY.Create(
      'containeranalysis.providers', providersId=provider_name)


def ParseProviderNote(note_id, provider_ref):
  """Create a provider Note ref, suitable for attaching an Occurrence to."""
  provider_name = provider_ref.Name()
  return resources.REGISTRY.Parse(
      note_id, {'providersId': provider_name},
      collection='containeranalysis.providers.notes')


def NoteId(artifact_url, public_key, signature):
  """Returns Note id determined by supplied arguments."""
  digest = md5.new()
  digest.update(artifact_url)
  digest.update(public_key)
  digest.update(signature)
  artifact_url_md5 = base64.urlsafe_b64encode(digest.digest())
  return 'signature_test_{}'.format(artifact_url_md5)


def ReplaceImageUrlScheme(image_url, scheme):
  """Returns the passed `image_url` with the scheme replaced.

  Args:
    image_url: The URL to replace (or strip) the scheme from. (string)
    scheme: The scheme of the returned URL.  If this is an empty string or
      `None`, the scheme is stripped and the leading `//` of the resulting URL
      will be stripped off.
  Raises:
    BadImageUrlError: `image_url` isn't valid.
  """
  scheme = scheme or ''
  parsed_url = urlparse.urlparse(image_url)

  # If the URL has a scheme but not a netloc, then it must have looked like
  # 'scheme:///foo/bar', which is invalid for the purpose of attestation.
  if parsed_url.scheme and not parsed_url.netloc:
    raise BadImageUrlError(
        "Image URL '{image_url}' is invalid because it does not have a host "
        'component.'.format(image_url=image_url))

  # If there is neither a scheme nor a netloc, this means that an unqualified
  # URL was passed, like 'gcr.io/foo/bar'.  In this case we canonicalize the URL
  # by prefixing '//', which will cause urlparse it to correctly pick up the
  # netloc.
  if not parsed_url.netloc:
    parsed_url = urlparse.urlparse('//{}'.format(image_url))

  # Finally, we replace the scheme and generate the URL.  If we were stripping
  # the scheme, the result will be prefixed with '//', which we strip off.  If
  # the scheme is non-empty, the lstrip is a no-op.
  return parsed_url._replace(scheme=scheme).geturl().lstrip('/')


def MakeSignaturePayload(container_image_url):
  """Creates a dict representing a JSON signature object to sign.

  Args:
    container_image_url: See `containerregistry.client.docker_name.Digest` for
      artifact URL validation and parsing details.  `container_image_url` must
      be a fully qualified image URL with a valid sha256 digest.

  Returns:
    Dictionary of nested dictionaries and strings, suitable for passing to
    `json.dumps` or similar.
  """
  url = ReplaceImageUrlScheme(image_url=container_image_url, scheme='')
  try:
    repo_digest = docker_name.Digest(url)
  except docker_name.BadNameException as e:
    raise BadImageUrlError(e)
  return {
      'critical': {
          'identity': {
              'docker-reference': str(repo_digest.as_repository()),
          },
          'image': {
              'docker-manifest-digest': repo_digest.digest,
          },
          'type': 'Google cloud binauthz container signature',
      },
  }


def NormalizeArtifactUrl(artifact_url):
  """Normalizes given URL by ensuring the scheme is https."""
  url_without_scheme = ReplaceImageUrlScheme(artifact_url, scheme='')
  try:
    # The validation logic in `docker_name` silently produces incorrect results
    # if the passed URL has a scheme.
    docker_name.Digest(url_without_scheme)
  except docker_name.BadNameException as e:
    raise BadImageUrlError(e)
  return ReplaceImageUrlScheme(artifact_url, scheme='https')
