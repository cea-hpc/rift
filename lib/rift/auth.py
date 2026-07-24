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

_EXPIRATION_FMT = "%Y-%m-%dT%H:%M:%SZ"


class AuthState:
    """
    Persisted authentication credentials (credentials file payload).
    """

    def __init__(
        self,
        idp_token=None,
        idp_token_expiration=None,
        access_key_id=None,
        secret_access_key=None,
        session_token=None,
        expiration=None,
    ):
        # IDP token and expiration
        self.idp_token = idp_token
        self.idp_token_expiration = idp_token_expiration
        # S3 credentials
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.session_token = session_token
        self.expiration = expiration

    @classmethod
    def from_dict(cls, data):
        """Build AuthState from a credentials-file dict."""
        if not data:
            return cls()
        return cls(
            idp_token=data.get("idp_token"),
            idp_token_expiration=data.get("idp_token_expiration"),
            access_key_id=data.get("access_key_id"),
            secret_access_key=data.get("secret_access_key"),
            session_token=data.get("session_token"),
            expiration=data.get("expiration"),
        )

    def to_dict(self):
        """Return dict suitable for JSON persistence; omit unset fields."""
        data = {
            "idp_token": self.idp_token,
            "idp_token_expiration": self.idp_token_expiration,
            "access_key_id": self.access_key_id,
            "secret_access_key": self.secret_access_key,
            "session_token": self.session_token,
            "expiration": self.expiration,
        }
        return {key: value for key, value in data.items() if value is not None}

    def clear_expired(self):
        """
        Drop expired S3 and/or IDP fields.
        Returns True if anything was scrubbed.
        """
        now = datetime.datetime.now()
        updated = False

        # Check S3 credentials expiration
        if self.expiration:
            expiration = datetime.datetime.strptime(self.expiration, _EXPIRATION_FMT)
            if expiration > now:
                logging.info("found existing, valid S3 credentials")
            else:
                logging.info("info: found existing, expired S3 credentials")
                self.expiration = None
                self.access_key_id = None
                self.secret_access_key = None
                self.session_token = None
                updated = True

        # Check IDP token expiration
        if self.idp_token_expiration:
            expiration = datetime.datetime.strptime(
                self.idp_token_expiration, _EXPIRATION_FMT
            )
            if expiration > now:
                logging.info("found existing, valid idp access token")
            else:
                logging.info("found existing, expired idp access token")
                self.idp_token = None
                self.idp_token_expiration = None
                updated = True

        return updated

    @classmethod
    def restore(cls, path):
        """
        Load credentials file at path.
        On JSON decode failure, start empty.
        Run clear_expired(); if scrubbed, rewrite file via save().
        Return AuthState instance.
        """
        with open(path, "r", encoding="utf-8") as fs:
            data = fs.read()

        raw = {}
        try:
            raw = json.loads(data)
        except json.JSONDecodeError as e:
            logging.info("failed to decode json from existing credentials file: %s", e)

        state = cls.from_dict(raw)
        if state.clear_expired():
            state.save(path)
        return state

    def save(self, path):
        """
        Persist to_dict() to path with mode 0600.
        """
        os.umask(0)
        fd = os.open(
            path=path,
            flags=os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            mode=0o600,
        )
        with open(fd, "w", encoding="utf-8") as fs:
            json.dump(self.to_dict(), fs, indent=2, sort_keys=True)

    def has_s3_credentials(self):
        """Return True if all S3 credential fields are set."""
        return None not in (
            self.access_key_id,
            self.secret_access_key,
            self.session_token,
        ) and "" not in (
            self.access_key_id,
            self.secret_access_key,
            self.session_token,
        )

    def s3_expiration_dt(self):
        """Parse expiration string to datetime, or None if unset."""
        if not self.expiration:
            return None
        return datetime.datetime.strptime(self.expiration, _EXPIRATION_FMT)

    def s3_expiration_str(self):
        """
        Returns a human readable time string of auth token, if possible.
        If token expiration date is not set, returns an empty string.
        """
        expiration_dt = self.s3_expiration_dt()
        if not expiration_dt:
            return ""
        return expiration_dt.strftime("%a %b %d %H:%M:%S %Y")


class Auth:
    """
    Config: Manage rift authentication
        This class manages rift authentication
    """

    def __init__(self, config):
        self.idp_app_token = config.get("idp_app_token")
        if self.idp_app_token is None:
            msg = "authentication requires presence of idp_app_token config"
            raise RiftError(msg)
        self.idp_auth_endpoint = config.get("idp_auth_endpoint")
        self.s3_auth_endpoint = config.get("s3_auth_endpoint")
        self.credentials_file = os.path.expanduser(config.get("s3_credential_file"))

        self.state = AuthState()

    # Step 1: Get OpenID token
    def get_idp_token(self):
        """
        Get OpenID Token
        """
        if self.state.idp_token:
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
            password = getpass.getpass("Password: ")

        data = {
            "client_id": "minio",
            "grant_type": "password",
            "username": user,
            "password": password,
            "client_secret": client_secret,
        }

        res = requests.post(
            self.idp_auth_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=60,
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

        self.state.idp_token_expiration = expire_dt.strftime(_EXPIRATION_FMT)
        self.state.idp_token = token
        self.state.save(self.credentials_file)

        return True

    def get_idp_token_noninteractive(self):
        """
        Return cached OpenID token from environment or state file without
        prompting user. Raise RiftError if token is missing or expired.
        """

        token = os.environ.get("RIFT_AUTH_IDP_TOKEN")
        if token:
            logging.debug("fetched idp token from environment")
            return token

        if not os.path.isfile(self.credentials_file):
            raise RiftError(
                f"Missing authentication state file {self.credentials_file}. "
                "Run 'rift auth' first."
            )
        self.state = AuthState.restore(self.credentials_file)
        token = self.state.idp_token
        if not token:
            raise RiftError(
                "Missing idp_token in authentication state file "
                f"{self.credentials_file}. "
                "Run 'rift auth' first."
            )
        return token

    # Step 2: Get S3 credentials using token from (1)
    def get_s3_credentials(self):
        """
        Obtains an S3 credential using an already-obtained OpenID credential,
        unless an S3 credential is already available in auth object's state,
        in which case the credential is considered to have already been
        obtained.

        Returns True on success, False on failure.
        """
        if self.state.has_s3_credentials():
            return True

        if not self.s3_auth_endpoint:
            logging.error("missing required config parameter: s3_auth_endpoint")
            return False

        if not self.get_idp_token():
            logging.error("failed to get idp access token")
            return False

        data = {
            "Version": "2011-06-15",
            "Action": "AssumeRoleWithWebIdentity",
            "DurationSeconds": "86000",
            "WebIdentityToken": self.state.idp_token,
        }

        res = requests.post(
            self.s3_auth_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            verify=False,
            timeout=60,
        )

        res_xml = xmltodict.parse(res.text)

        creds = res_xml.get("AssumeRoleWithWebIdentityResponse")
        if not creds:
            msg = (
                "S3 credential response missing expected key: "
                "AssumeRoleWithWebIdentityResponse"
            )
            raise RiftError(msg)

        creds = creds.get("AssumeRoleWithWebIdentityResult")
        if not creds:
            msg = (
                "S3 credential response missing expected key: "
                "AssumeRoleWithWebIdentityResult"
            )
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

        self.state.access_key_id = access_key_id
        self.state.secret_access_key = secret_access_key
        self.state.session_token = session_token
        self.state.expiration = expiration

        self.state.save(self.credentials_file)

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
            msg = (
                "found AWS S3 variables in environment; will bypass credentials file\n"
            )
            msg += (
                "to allow use of credential file, please clear these "
                "environment variables:"
            )
            msg += " AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN"
            logging.info(msg)
            self.state.access_key_id = aws_access_key_id
            self.state.secret_access_key = aws_secret_access_key
            self.state.session_token = aws_session_token
            return True

        if os.path.isfile(self.credentials_file):
            logging.info("found credentials file: %s", self.credentials_file)
            self.state = AuthState.restore(self.credentials_file)
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
