#
# Copyright 2015, 2016, 2017  Human Longevity, Inc.
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
#

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import disdat.common
import disdat.resources
import disdat.utility.aws_s3 as aws
import docker
import infrastructure.dockerizer
import inspect
import logging
import os
import subprocess
import tempfile

_MODULE_NAME = inspect.getmodulename(__file__)

_DOCKERIZER_ROOT = os.path.dirname(inspect.getsourcefile(infrastructure.dockerizer))

_logger = logging.getLogger(__name__)


def dockerize(disdat_config, pipeline_root, pipeline_class_name, config_dir=None, os_type=None, os_version=None, build=True, push=False):
    """ Create a Docker image for running a pipeline.

    Args:
        disdat_config:
        pipeline_root: Root of the Python source tree containing the
        user-defined transform; must have a setuptools-style setup.py file.
        pipeline_class_name: The fully-qualified name of the pipeline
        class
        build:
        config_dir:
        push:

    Returns:

    """

    # Get configuration parameters
    image_os_type = os_type if os_type is not None else disdat_config.parser.get(_MODULE_NAME, 'os_type')
    image_os_version = os_version if os_version is not None else disdat_config.parser.get(_MODULE_NAME, 'os_version')
    docker_context = None

    if docker_context is None:
        docker_context = tempfile.mkdtemp(suffix=_MODULE_NAME)
    docker_makefile = os.path.join(_DOCKERIZER_ROOT, 'Makefile')
    _logger.debug('Using Docker context {}'.format(docker_context))

    # Populate the Docker context with the template containing dockerfiles,
    # entrypoints, etc.
    rsync_command = [
        'rsync',
        '-aq',  # Archive mode, no non-error messages
        '--exclude', '*.pyc',  # Don't copy any compiled Python files
        os.path.join(_DOCKERIZER_ROOT, 'context.template', ''),
        docker_context,
    ]
    subprocess.check_call(rsync_command)

    pipeline_image_name = disdat.common.make_pipeline_image_name(pipeline_class_name)
    DEFAULT_DISDAT_HOME = os.path.join('/', *os.path.dirname(disdat.dockerize.__file__).split('/')[:-1])
    DISDAT_HOME = os.getenv('DISDAT_HOME', DEFAULT_DISDAT_HOME)

    if build:
        build_command = [
            'make',  # XXX really need to check that this is GNU make
            '-f', docker_makefile,
            'PIPELINE_IMAGE_NAME={}'.format(pipeline_image_name),
            'DOCKER_CONTEXT={}'.format(docker_context),
            'DISDAT_ROOT={}'.format(os.path.join(DISDAT_HOME)),  # XXX YUCK
            'PIPELINE_ROOT={}'.format(pipeline_root),
            'PIPELINE_CLASS={}'.format(pipeline_class_name),
            'OS_TYPE={}'.format(image_os_type),
            'OS_VERSION={}'.format(image_os_version),
        ]
        if config_dir is not None:
            build_command.append('CONFIG_ROOT={}'.format(config_dir))
        subprocess.check_call(build_command)

    if push:
        docker_client = docker.from_env()
        repository_name_prefix = disdat_config.parser.get('docker', 'repository_prefix')
        repository_name = disdat.common.make_pipeline_repository_name(repository_name_prefix, pipeline_class_name)
        # Figure out the fully-qualified repository name, i.e., the name
        # including the registry.
        registry_name = disdat_config.parser.get('docker', 'registry').strip('/')
        if registry_name == '*ECR*':
            policy_resource_name = None
            if disdat_config.parser.has_option('docker', 'ecr_policy'):
                policy_resource_name = disdat_config.parser.get('docker', 'ecr_policy')
            fq_repository_name = aws.ecr_create_fq_respository_name(
                repository_name,
                policy_resource_package=disdat.resources,
                policy_resource_name=policy_resource_name
            )
        else:
            fq_repository_name = '{}/{}'.format(registry_name, repository_name)
        auth_config = None
        if disdat_config.parser.has_option('docker', 'ecr_login') or registry_name == '*ECR*':
            auth_config = aws.ecr_get_auth_config()
        docker_client.api.tag(pipeline_image_name, fq_repository_name)
        for line in docker_client.images.push(fq_repository_name, auth_config=auth_config, stream=True):
            if 'error' in line:
                raise RuntimeError(line)
            else:
                print line


def main(disdat_config, args):
    """Run the dockerize command with some parameters from the command line.

    Parameters:
        disdat_config:
        args:

    Returns:
        ()
    """

    dockerize(
        disdat_config,
        args.pipe_root,
        args.pipe_cls,
        config_dir=args.config_dir,
        os_type=args.os_type,
        os_version=args.os_version,
        build=args.build,
        push=args.push,
    )
