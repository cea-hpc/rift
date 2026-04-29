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
import shutil
import urllib
import logging
import time

from datetime import datetime, timezone

from rift import RiftError

def message(msg):
    """
    helper function to print a log message
    """
    print(f"> {msg}")

def banner(title):
    """
    helper function to print a banner
    """
    print(f"** {title} **")

def download_file(url, output, max_size=None, retries=0, bearer_token=None):
    """
    Download file pointed by url and save it in output path. Convert
    potential urllib download errors into RiftError.

    When max_size is set, the server Content-Length header is checked against
    max_size before streaming the body (single GET).

    If retries is set and is greater than 0, retry the download up to retries
    times.

    If bearer_token is set, send Authorization: Bearer <token> on the request.
    """

    req = urllib.request.Request(url)
    if bearer_token:
        req.add_header('Authorization', f'Bearer {bearer_token}')

    for attempt in range(retries + 1):
        try:
            if max_size is not None:
                with urllib.request.urlopen(req) as opened_url:
                    meta = opened_url.info()
                    length = meta["Content-Length"]
                    if (isinstance(length, str) and int(length) > max_size):
                        raise RiftError(
                            f"'{url}' has a size of '{length}' bytes, larger than "
                            f"max size '{max_size}', skipping download",
                        )
                    with open(output, 'wb') as out_fh:
                        shutil.copyfileobj(opened_url, out_fh)
                    break
            else:
                with urllib.request.urlopen(req) as opened_url:
                    with open(output, 'wb') as out_fh:
                        shutil.copyfileobj(opened_url, out_fh)
                break

        except (urllib.error.HTTPError, urllib.error.URLError) as error:
            if attempt == retries:
                # maximum retries exceeded
                raise RiftError(
                    f"Error while downloading {url}: {str(error)}"
                ) from error

            delay = (attempt + 1) * 3
            logging.info(
                "Error while downloading %s: %s, will retry in %s seconds…",
                url,
                error,
                delay
            )
            time.sleep(delay)

def last_modified(url, bearer_token=None):
    """
    Return the mtime of the URL using the Last-Modified header. By convention,
    Last-Modified is always in GMT/UTC timezone. Raises RiftError when unable to
    get or convert Last-Modified header to timestamp.

    If bearer_token is set, send Authorization: Bearer <token> on the request.
    """
    req = urllib.request.Request(url, method='HEAD')
    if bearer_token:
        req.add_header('Authorization', f'Bearer {bearer_token}')

    try:
        with urllib.request.urlopen(req) as response:
            return int(datetime.strptime(
                response.getheader('Last-Modified'), '%a, %d %b %Y %H:%M:%S %Z'
            ).replace(tzinfo=timezone.utc).timestamp())
    except urllib.error.URLError as err:
        raise RiftError(
            f"Unable to send HTTP HEAD request for URL {url}: {err}"
        ) from err
    except TypeError as err:
        raise RiftError(
            f"Unable to get Last-Modified header for URL {url}"
        ) from err
    except ValueError as err:
        raise RiftError(
            f"Unable to convert Last-Modified header to datetime for URL {url}"
        ) from err

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
