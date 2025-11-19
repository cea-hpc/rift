#
# Copyright (C) 2014-2025 CEA
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
Auth:
    This package manage rift s3 authentication
"""
import datetime
import getpass
import json
import logging
import os
import sys

import requests
import urllib3
import xmltodict

from rift import RiftError

urllib3.disable_warnings()

class Auth:
    """
    Config: Manage rift authentication
        This class manages rift authentication
    """
    def __init__(self, config):
        self.idp_app_token = config.get('idp_app_token')
        if self.idp_app_token is None:
            msg = "authentication requires presence of idp_app_token config"
            raise RiftError(msg)
        self.idp_auth_endpoint = config.get('idp_auth_endpoint')
        self.s3_auth_endpoint = config.get('s3_auth_endpoint')
        self.credentials_file = os.path.expanduser(config.get('s3_credential_file'))

        self.config = {}
        self.expiration_dt = ""

    def get_expiration_timestr(self):
        """
        Returns a human readable time string of auth token, if possible.
        If token expiration date is not set, returns an emptry string
        """
        if not self.expiration_dt:
            return ""
        return self.expiration_dt.strftime("%a %b %d %H:%M:%S %Y")

    def restore_state(self):
        """
        Loads data from existing credentials file, if one exists.
        If credentials file contains expired data, remove expired items from file.
        """

        with open(self.credentials_file, 'r', encoding="utf-8") as fs:
            data = fs.read()

            config = {}
            try:
                config = json.loads(data)
            except json.JSONDecodeError as e:
                logging.info("failed to decode json from existing credentials file: %s", e)

            update_authfile = False

            expiry = config.get("expiration")
            if expiry:
                expiration = datetime.datetime.strptime(expiry, "%Y-%m-%dT%H:%M:%SZ")
                if expiration > datetime.datetime.now():
                    # S3 credentials are still valid
                    logging.info("found existing, valid S3 credentials")
                    self.expiration_dt = expiration
                else:
                    # S3 credentials expired
                    logging.info("info: found existing, expired S3 credentials")
                    config.pop("expiration", None)
                    config.pop("access_key_id", None)
                    config.pop("secret_access_key", None)
                    config.pop("session_token", None)
                    update_authfile = True

            idp_expiry = config.get("idp_token_expiration")
            if idp_expiry:
                expiration = datetime.datetime.strptime(idp_expiry, "%Y-%m-%dT%H:%M:%SZ")
                if expiration > datetime.datetime.now():
                    # IDP access token is still valid
                    logging.info("found existing, valid idp access token")
                else:
                    # IDP access token has expired
                    logging.info("found existing, expired idp access token")
                    config.pop("idp_token")
                    config.pop("idp_token_expiration")
                    update_authfile = True

            self.config = config

            if update_authfile:
                self.save_state()

    def save_state(self):
        """
        Saves auth object config information to credentials file.
        """
        os.umask(0)
        fd = os.open(
            path = self.credentials_file,
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            mode=0o600
        )
        with open(fd, "w", encoding="utf-8") as fs:
            json.dump(self.config, fs, indent=2, sort_keys=True)

    # Step 1: Get OpenID token
    def get_idp_token(self):
        """
        Get OpenID Token
        """
        # curl \
        #  -d "client_id=minio" \
        #  -d "grant_type=password" \
        #  -d "username=$INTI_LOGIN" \
        #  -d "password=$INTI_PASSWORD" \
        #  -H "Content-Type: application/x-www-form-urlencoded" \
        #  "https://idp.ccc.ocre.cea.fr/auth/realms/minio/protocol/openid-connect/token"

        token = self.config.get("idp_token")
        if token:
            logging.info("retrieved existing idp_token from auth file")
            return True

        if not self.idp_auth_endpoint:
            logging.error("missing required config parameter: idp_auth_endpoint")
            return False

        client_secret = self.idp_app_token

        user = os.environ.get("RIFT_AUTH_USER")
        if not user:
            default_user = getpass.getuser()
            user = input(f"Username [{default_user}]: ") or default_user

        password = os.environ.get("RIFT_AUTH_PASSWORD")
        if not password:
            password = getpass.getpass('Password: ')

        data = {
            'client_id': 'minio',
            'grant_type': 'password',
            'username': user,
            'password': password,
            'client_secret': client_secret,
        }

        res = requests.post(
            self.idp_auth_endpoint,
            data = data,
            headers = {"Content-Type": "application/x-www-form-urlencoded"},
            timeout = 60
        )

        js = res.json()

        token = js.get("access_token")
        if not token:
            msg = "received unexpected response while fetching idp access token:"
            msg += " missing field 'access_token'"
            raise RiftError(msg)

        expires_in_sec = js.get("expires_in")
        if not expires_in_sec:
            msg = "received unexpected response while fetching idp access token:"
            msg += " missing field 'expires_in'"
            logging.info(msg)

        expire_dt = datetime.datetime.now() + datetime.timedelta(seconds=expires_in_sec)

        self.config["idp_token_expiration"] = expire_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.config["idp_token"] = token
        self.save_state()

        return True

    # Step 2: Get S3 credentials using token from (1)
    def get_s3_credentials(self):
        """
        Obtains an S3 credential using an already-obtained OpenID credential, unless
        an S3 credential is already available in auth object's config, in which case the credential
        is considered to have already been obtained.

        Returns True on success, False on failure.
        """
        # curl \
        #  -s \
        #  -X POST \
        #  https://annexe-forge.ccc.ocre.cea.fr \
        #  -H "Content-Type: application/x-www-form-urlencoded" \
        #  -d "Version=2011-06-15" \
        #  -d "Action=AssumeRoleWithWebIdentity" \
        #  -d "DurationSeconds=86000" \
        #  -d "WebIdentityToken=$ACCESS_TOKEN"
        access_key_id = self.config.get("access_key_id", "")
        secret_access_key = self.config.get("secret_access_key", "")
        session_token = self.config.get("session_token", "")

        if "" not in (access_key_id, secret_access_key, session_token):
            return True

        if not self.s3_auth_endpoint:
            logging.error("missing required config parameter: s3_auth_endpoint")
            return False

        if not self.get_idp_token():
            logging.error("failed to get idp access token")
            return False

        data = {
          'Version': '2011-06-15',
          'Action': 'AssumeRoleWithWebIdentity',
          'DurationSeconds': '86000',
          'WebIdentityToken': self.config["idp_token"],
        }

        res = requests.post(
            self.s3_auth_endpoint,
            data = data,
            headers = {"Content-Type": "application/x-www-form-urlencoded"},
            verify = False,
            timeout = 60
        )

        res_xml = xmltodict.parse(res.text)

        creds = res_xml.get("AssumeRoleWithWebIdentityResponse")
        if not creds:
            msg = "S3 credential response missing expected key: AssumeRoleWithWebIdentityResponse"
            raise RiftError(msg)

        creds = creds.get("AssumeRoleWithWebIdentityResult")
        if not creds:
            msg = "S3 credential response missing expected key: AssumeRoleWithWebIdentityResult"
            raise RiftError(msg)

        creds = creds.get("Credentials")
        if not creds:
            msg = "S3 credential response missing expected key: Credentials"
            raise RiftError(msg)

        access_key_id = creds.get("AccessKeyId", "")
        secret_access_key = creds.get("SecretAccessKey", "")
        session_token = creds.get("SessionToken", "")
        expiration = creds.get("Expiration", "")

        if "" in (access_key_id, secret_access_key, session_token, expiration):
            msg = "one or more expected credential values is missing: \n"
            msg += "AccessKeyId, SecretAccessKey, SessionToken, Expiration"
            raise RiftError(msg)

        self.config["access_key_id"] = access_key_id
        self.config["secret_access_key"] = secret_access_key
        self.config["session_token"] = session_token
        self.config["expiration"] = expiration

        self.expiration_dt = datetime.datetime.strptime(expiration, "%Y-%m-%dT%H:%M:%SZ")

        self.save_state()

        return True

    def authenticate(self):
        """
        Ensures S3 credentials are available.
        Returns True if S3 credentials are found, or False if not.

        This is the method auth object consumers should invoke to 
        ensure authentication credentials are available.
        """

        aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        aws_session_token = os.environ.get("AWS_SESSION_TOKEN")

        if None not in (aws_access_key_id, aws_secret_access_key):
            msg = "found AWS S3 variables in environment; will bypass credentials file\n"
            msg += "to allow use of credential file, please clear these environment variables:"
            msg += " AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN"
            logging.info(msg)
            self.config["access_key_id"] = aws_access_key_id
            self.config["secret_access_key"] = aws_secret_access_key
            self.config["session_token"] = aws_session_token
            return True

        if os.path.isfile(self.credentials_file):
            logging.info("found credentials file: %s", self.credentials_file)
            self.restore_state()
        else:
            base = os.path.dirname(self.credentials_file)
            if os.path.exists(base):
                if not os.path.isdir(base):
                    raise RiftError(f"{base} should be a directory")
            else:
                os.makedirs(base)

        if not self.get_s3_credentials():
            logging.error("failed to obtain S3 credentials")
            sys.exit(1)

        return True
