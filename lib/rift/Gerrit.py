#
# Copyright (C) 2014-2016 CEA
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
Helper to push REST review to Gerrit Code Reviewer server.
"""

import json
import logging
try:
    import urllib2 as urllib
except ImportError:
    import urllib.request as urllib

import ssl
from rift import RiftError

class Review():
    """Gerrit review."""

    def __init__(self):
        self.labels = {'W': 'warning', 'E': 'error'}
        self.stats = {'E': 0}
        self.msg_header = 'Rift review'
        self.comments = {}
        self.validated = True

    def add_comment(self, filepath, line, label, message):
        """Define comment in gerrit review process"""
        self.stats.setdefault(label, 0)
        self.stats[label] += 1

        msg = f"({self.labels[label]}) {message}"
        comment = {
            'message': msg,
        }
        if line is not None:
            comment['line'] = line
        self.comments.setdefault(filepath, []).append(comment)

    def _message(self):
        stats = ((cnt, self.labels[code])
                 for code, cnt in list(self.stats.items()))
        msg = ", ".join(f"{cnt} {label}(s)" for cnt, label in stats)
        return f"{self.msg_header}: {msg}"

    def invalidate(self):
        """Review is considered as invalide, checked commit is not approved"""
        self.validated = False

    def push(self, config, changeid, revid):
        """Send REST request to Gerrit server from config"""
        auth_methods = ('digest', 'basic')

        gerrit_config = config.get('gerrit')
        if gerrit_config is None:
            raise RiftError("Gerrit configuration is not defined")

        realm = gerrit_config.get('realm')
        server = gerrit_config.get('server')
        username = gerrit_config.get('username')
        password = gerrit_config.get('password')
        auth_method = gerrit_config.get('auth_method', 'basic')

        if realm is None:
            raise RiftError("Gerrit realm is not defined")
        if server is None and gerrit_config.get('url') is None:
            raise RiftError("Gerrit url is not defined")
        if username is None:
            raise RiftError("Gerrit username is not defined")
        if password is None:
            raise RiftError("Gerrit password is not defined")
        if auth_method not in auth_methods:
            raise RiftError(f"Gerrit auth_method is not correct (supported {auth_methods})")

        # Set a default url if only gerrit_server was defined
        url = gerrit_config.get('url', f"https://{server}")

        # FIXME: Don't check certificate
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        #https_sslv3_handler = urllib.HTTPSHandler(context=ssl.SSLContext(ssl.PROTOCOL_SSLv3))
        https_sslv3_handler = urllib.HTTPSHandler(context=ctx)

        api_url = f"{url}/gerrit/a/changes/{changeid}/revisions/{revid}/review"
        if auth_method == 'digest':
            authhandler = urllib.HTTPDigestAuthHandler()
            authhandler.add_password(realm, server, username, password)
        elif auth_method == 'basic':
            pw_mgr = urllib.HTTPPasswordMgrWithDefaultRealm()
            # this creates a password manager
            pw_mgr.add_password(None, url, username, password)
            authhandler = urllib.HTTPBasicAuthHandler(pw_mgr)

        opener = urllib.build_opener(authhandler, https_sslv3_handler)

        urllib.install_opener(opener)

        # Create request data structure
        request = {
            "message": self._message(),
            "comments": self.comments,
        }
        if self.validated:
            request['labels'] = {"Code-Review": '+1'}
        data = json.dumps(request, indent=2)


        logging.debug("Sending review request to %s", api_url)
        logging.debug("Request content: %s", data)

        req = urllib.Request(api_url, data.encode("utf8"),
                             {'Content-Type': 'application/json'})
        req.get_method = lambda: 'POST'
        urllib.urlopen(req).read()
