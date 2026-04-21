import json
import os
import re
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from rift import RiftError
from rift.auth import Auth

from .TestUtils import make_temp_file


class AuthTest(unittest.TestCase):
    """Unit tests for rift.auth.Auth; add new test groups as methods here."""

    def setUp(self):
        self._cred_tmp = make_temp_file("{}", delete=False, suffix=".json")
        self._cred_path = self._cred_tmp.name
        self._cred_tmp.close()
        self._minimal_config = {
            "idp_app_token": "app-token",
            "s3_credential_file": self._cred_path,
        }

    def tearDown(self):
        if os.path.isfile(self._cred_path):
            os.unlink(self._cred_path)

    def _write_state(self, data):
        with open(self._cred_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_get_idp_token_noninteractive_env_token(self):
        self._write_state({})
        auth = Auth(self._minimal_config)
        with patch.dict(os.environ, {"RIFT_AUTH_IDP_TOKEN": "from-env"}):
            with self.assertLogs(level="DEBUG") as logs:
                self.assertEqual(auth.get_idp_token_noninteractive(), "from-env")
        self.assertIn("fetched idp token from environment", "\n".join(logs.output))

    def test_get_idp_token_noninteractive_missing_credentials_file(self):
        missing = self._cred_path + ".missing"
        self._minimal_config["s3_credential_file"] = missing
        auth = Auth(self._minimal_config)
        with self.assertRaisesRegex(
            RiftError,
            rf"Missing authentication state file {re.escape(missing)}\. "
            r"Run 'rift auth' first\.",
        ):
            auth.get_idp_token_noninteractive()

    def test_get_idp_token_noninteractive_missing_idp_token(self):
        self._write_state({})
        auth = Auth(self._minimal_config)
        with self.assertRaisesRegex(
            RiftError,
            rf"Missing idp_token in authentication state file {re.escape(self._cred_path)}\. "
            r"Run 'rift auth' first\.",
        ):
            auth.get_idp_token_noninteractive()

    def test_get_idp_token_noninteractive_state_file(self):
        exp = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_state(
            {
                "idp_token": "tok-from-file",
                "idp_token_expiration": exp,
            }
        )
        auth = Auth(self._minimal_config)
        self.assertEqual(auth.get_idp_token_noninteractive(), "tok-from-file")

    def test_get_idp_token_noninteractive_expired_token(self):
        exp = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_state(
            {
                "idp_token": "expired",
                "idp_token_expiration": exp,
            }
        )
        auth = Auth(self._minimal_config)
        with self.assertRaisesRegex(
            RiftError,
            rf"Missing idp_token in authentication state file {re.escape(self._cred_path)}\. "
            r"Run 'rift auth' first\.",
        ):
            auth.get_idp_token_noninteractive()
