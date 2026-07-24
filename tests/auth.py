import json
import os
import re
import stat
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from rift import RiftError
from rift.auth import Auth, AuthState

from .test_utils import make_temp_file


class AuthStateTest(unittest.TestCase):
    """Unit tests for rift.auth.AuthState."""

    def setUp(self):
        self._cred_tmp = make_temp_file("{}", delete=False, suffix=".json")
        self._cred_path = self._cred_tmp.name
        self._cred_tmp.close()

    def tearDown(self):
        if os.path.isfile(self._cred_path):
            os.unlink(self._cred_path)

    def _write_state(self, data):
        with open(self._cred_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_from_dict_to_dict_roundtrip(self):
        """from_dict then to_dict preserves all credential fields."""
        data = {
            "idp_token": "tok",
            "idp_token_expiration": "2099-01-01T00:00:00Z",
            "access_key_id": "ak",
            "secret_access_key": "sk",
            "session_token": "st",
            "expiration": "2099-01-02T00:00:00Z",
        }
        state = AuthState.from_dict(data)
        self.assertEqual(state.to_dict(), data)

    def test_to_dict_omits_none(self):
        """to_dict drops unset (None) fields from the persisted payload."""
        state = AuthState(idp_token="tok")
        self.assertEqual(state.to_dict(), {"idp_token": "tok"})

    def test_restore_scrubs_expired_and_rewrites(self):
        """restore clears expired IDP/S3 fields and rewrites the credentials file."""
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_state(
            {
                "idp_token": "expired",
                "idp_token_expiration": past,
                "access_key_id": "ak",
                "secret_access_key": "sk",
                "session_token": "st",
                "expiration": past,
            }
        )
        with self.assertLogs(level="INFO") as logs:
            restored = AuthState.restore(self._cred_path)
        self.assertIn(
            "found existing, expired S3 credentials",
            "\n".join(logs.output),
        )
        self.assertIn(
            "found existing, expired idp access token",
            "\n".join(logs.output),
        )
        self.assertIsNone(restored.idp_token)
        self.assertIsNone(restored.idp_token_expiration)
        self.assertIsNone(restored.access_key_id)
        self.assertIsNone(restored.secret_access_key)
        self.assertIsNone(restored.session_token)
        self.assertIsNone(restored.expiration)

        with open(self._cred_path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk, {})

    def test_restore_invalid_json(self):
        """restore tolerates invalid JSON and returns an empty AuthState."""
        with open(self._cred_path, "w", encoding="utf-8") as f:
            f.write("not-json")
        with self.assertLogs(level="INFO") as logs:
            restored = AuthState.restore(self._cred_path)
        self.assertIsNone(restored.idp_token)
        self.assertIn(
            "failed to decode json from existing credentials file",
            "\n".join(logs.output),
        )

    def test_save_and_restore(self):
        """save writes mode 0600; restore reloads valid credentials."""
        exp = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = AuthState(
            idp_token="tok-from-file",
            idp_token_expiration=exp,
            access_key_id="ak",
            secret_access_key="sk",
            session_token="st",
            expiration=exp,
        )
        state.save(self._cred_path)
        mode = stat.S_IMODE(os.stat(self._cred_path).st_mode)
        self.assertEqual(mode, 0o600)

        restored = AuthState.restore(self._cred_path)
        self.assertEqual(restored.idp_token, "tok-from-file")
        self.assertEqual(restored.access_key_id, "ak")
        self.assertTrue(restored.has_s3_credentials())
        self.assertIsNotNone(restored.s3_expiration_dt())

    def test_has_s3_credentials_true(self):
        """has_s3_credentials is True when access, secret, and session are set."""
        state = AuthState(
            access_key_id="ak",
            secret_access_key="sk",
            session_token="st",
        )
        self.assertTrue(state.has_s3_credentials())

    def test_has_s3_credentials_false_when_missing(self):
        """has_s3_credentials is False when any S3 field is unset."""
        self.assertFalse(AuthState().has_s3_credentials())
        self.assertFalse(
            AuthState(access_key_id="ak", secret_access_key="sk").has_s3_credentials()
        )

    def test_has_s3_credentials_false_when_empty_string(self):
        """has_s3_credentials is False when an S3 field is an empty string."""
        state = AuthState(
            access_key_id="ak",
            secret_access_key="sk",
            session_token="",
        )
        self.assertFalse(state.has_s3_credentials())

    def test_s3_expiration_dt_unset(self):
        """s3_expiration_dt returns None when expiration is unset."""
        self.assertIsNone(AuthState().s3_expiration_dt())

    def test_s3_expiration_dt_parses(self):
        """s3_expiration_dt parses the ISO UTC expiration string."""
        state = AuthState(expiration="2099-01-02T03:04:05Z")
        self.assertEqual(
            state.s3_expiration_dt(),
            datetime(2099, 1, 2, 3, 4, 5),
        )

    def test_s3_expiration_str_unset(self):
        """s3_expiration_str returns an empty string when expiration is unset."""
        self.assertEqual(AuthState().s3_expiration_str(), "")

    def test_s3_expiration_str_formats(self):
        """s3_expiration_str returns a human-readable local-style timestamp."""
        state = AuthState(expiration="2099-01-02T03:04:05Z")
        self.assertEqual(
            state.s3_expiration_str(),
            datetime(2099, 1, 2, 3, 4, 5).strftime("%a %b %d %H:%M:%S %Y"),
        )


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
            (
                r"Missing idp_token in authentication state file "
                rf"{re.escape(self._cred_path)}\. "
                r"Run 'rift auth' first\."
            ),
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
            (
                r"Missing idp_token in authentication state file "
                rf"{re.escape(self._cred_path)}\. "
                r"Run 'rift auth' first\."
            ),
        ):
            auth.get_idp_token_noninteractive()
