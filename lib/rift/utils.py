#
# Copyright (C) 2024 CEA
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
Set of utilities used in multiple Rift modules.
"""

import os
import urllib

from rift import RiftError

def download_file(url, output):
    """
    Download file pointed by url and save it in output path. Convert
    potential urllib download errors into RiftError.
    """
    try:
        urllib.request.urlretrieve(url, output)
    except urllib.error.HTTPError as error:
        raise RiftError(
            f"HTTP error while downloading {url}: {str(error)}"
        ) from error
    except urllib.error.URLError as error:
        raise RiftError(
            f"URL error while downloading {url}: {str(error)}"
        ) from error

def setup_dl_opener(proxy, no_proxy, fake_user_agent=True):
    """
    Setup urllib handler/opener with proxy, no_proxy settings. Also set fake
    user agent in requests headers, to emulate real browser and avoid potential
    filters configured on server side, when fake_user_agent is True.
    """

    handlers = []
    if proxy:
        handlers = [
            urllib.request.ProxyHandler({'http' : proxy, 'https': proxy})
        ]
    # If no_proxy is defined, set environment variable accordingly to
    # make urllib.request.ProxyHandler skip proxy for these targeted
    # hosts.
    if no_proxy is not None:
        os.environ['no_proxy'] = no_proxy
    opener = urllib.request.build_opener(*handlers)
    if fake_user_agent:
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
    urllib.request.install_opener(opener)

def removesuffix(input_string, suffix):
    """
    The removesuffix method was introduced in python 3.9,
    to preserve compatibility with older version, this is
    a reimplementation
    """
    if suffix and input_string.endswith(suffix):
        return input_string[:-len(suffix)]
    return input_string

