#
# Copyright (C) 2026 CEA
#
# This file is part of Rift project.
#
# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software.  You can  use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.
#

"""
CLI for the repos-token-proxy standalone executable.
"""

import argparse
import logging
import platform
import signal

from rift import RiftError
from rift.config import Config
from rift.proxy import AuthenticatedRepositoryProxyRuntime
from rift.repository import ProjectArchRepositories


def make_parser():
    """Create command line parser for repos-token-proxy."""
    parser = argparse.ArgumentParser(
        prog="repos-token-proxy",
        description="Launch the IDP token repository proxy server",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase output verbosity (twice for debug)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="binding host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="binding port (default: 0, ephemeral)",
    )
    parser.add_argument(
        "config",
        metavar="CONFIG",
        help="path to project configuration file",
    )
    return parser


def main(args=None):
    """Main code of 'repos-token-proxy'."""
    args = make_parser().parse_args(args)

    logging.basicConfig(
        format="%(levelname)-8s %(message)s", level=logging.WARNING - args.verbose * 10
    )

    runtime = None
    try:
        config = Config()
        config.ALLOW_MISSING = False
        config.load(args.config)

        repos = (
            ProjectArchRepositories(config, platform.machine()).for_format("rpm").all
        )
        runtime = AuthenticatedRepositoryProxyRuntime(config, repos)
        if not runtime.required:
            raise RiftError(
                "No repositories with auth: idp_token found in configuration"
            )

        runtime.start(host=args.host, port=args.port)
        for repo in runtime.repositories.values():
            logging.info(
                "Proxying repository %s -> %s",
                repo.name,
                runtime.repo_url(repo, args.host),
            )

        # Block until interrupted; signal handlers raise KeyboardInterrupt on
        # SIGTERM so cleanup shares the same path as Ctrl-C.
        def _stop_signal(_signum, _frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, _stop_signal)
        signal.pause()

    except (RiftError, IOError, OSError) as exp:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            raise
        logging.error(str(exp))
        return 1
    except KeyboardInterrupt:
        logging.info("Interrupted. Stopping repository proxy...")
    finally:
        if runtime is not None:
            runtime.stop()

    return 0
