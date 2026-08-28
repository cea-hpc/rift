import base64
import json
import os
import re
import stat
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from rift import RiftError
from rift.auth import Auth, AuthState, jwt_expiration_dt

from .test_utils import make_temp_file


def _make_jwt(payload):
    """Build a dummy unsigned JWT-like string with the given payload dict."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode("ascii")
    body = (
        base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )
    return f"{header}.{body}.sig"


class JwtExpirationDtTest(unittest.TestCase):
    """Unit tests for jwt_expiration_dt helper."""

    def test_reads_exp(self):
        exp = int((datetime.now() + timedelta(hours=1)).timestamp())
        token = _make_jwt({"exp": exp})
        self.assertEqual(jwt_expiration_dt(token), datetime.fromtimestamp(exp))

    def test_non_jwt_returns_none(self):
        self.assertIsNone(jwt_expiration_dt("not-a-jwt"))
        self.assertIsNone(jwt_expiration_dt(None))

    def test_missing_exp_returns_none(self):
        self.assertIsNone(jwt_expiration_dt(_make_jwt({"sub": "user"})))


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
            "idp_refresh_token": "refresh",
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
                "idp_refresh_token": "refresh",
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
        self.assertIsNone(restored.idp_refresh_token)
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
        exp = datetime.now() + timedelta(days=1)
        state = AuthState(
            idp_token="tok-from-file",
            idp_token_expiration=exp,
            idp_refresh_token="refresh-from-file",
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
        self.assertEqual(restored.idp_refresh_token, "refresh-from-file")
        self.assertEqual(restored.access_key_id, "ak")
        self.assertTrue(restored.has_s3_credentials())
        self.assertIsInstance(restored.expiration, datetime)
        self.assertIsInstance(restored.idp_token_expiration, datetime)
        self.assertIsNotNone(restored.expiration)

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

    def test_s3_expiration_str_unset(self):
        """s3_expiration_str returns an empty string when expiration is unset."""
        self.assertEqual(AuthState().s3_expiration_str(), "")

    def test_s3_expiration_str_formats(self):
        """s3_expiration_str returns a human-readable local-style timestamp."""
        exp = datetime(2099, 1, 2, 3, 4, 5)
        state = AuthState(expiration=exp)
        self.assertEqual(
            state.s3_expiration_str(),
            exp.strftime("%a %b %d %H:%M:%S %Y"),
        )

    def test_idp_seconds_remaining(self):
        """idp_seconds_remaining reflects stored datetime expiry."""
        self.assertIsNone(AuthState().idp_seconds_remaining())
        future = datetime.now() + timedelta(seconds=120)
        state = AuthState(idp_token_expiration=future)
        remaining = state.idp_seconds_remaining()
        self.assertIsNotNone(remaining)
        self.assertGreater(remaining, 100)
        self.assertLess(remaining, 130)


class AuthTest(unittest.TestCase):
    """Unit tests for rift.auth.Auth; add new test groups as methods here."""

    def setUp(self):
        self._cred_tmp = make_temp_file("{}", delete=False, suffix=".json")
        self._cred_path = self._cred_tmp.name
        self._cred_tmp.close()
        self._minimal_config = {
            "idp_app_token": "app-token",
            "s3_credential_file": self._cred_path,
            "idp_auth_endpoint": "https://idp.example/token",
            "idp_token_refresh_threshold": 300,
        }

    def tearDown(self):
        if os.path.isfile(self._cred_path):
            os.unlink(self._cred_path)

    def _write_state(self, data):
        with open(self._cred_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @patch("rift.auth.requests.post")
    def test_ensure_idp_token_fresh_near_expiry_without_refresh_skips(self, mock_post):
        auth = Auth(self._minimal_config)
        auth.state.idp_token_expiration = datetime.now() + timedelta(seconds=100)
        auth._ensure_idp_token_fresh()
        mock_post.assert_not_called()

    @patch("rift.auth.requests.post")
    def test_ensure_idp_token_fresh_above_threshold_skips_refresh(self, mock_post):
        auth = Auth(self._minimal_config)
        auth.state.idp_token_expiration = datetime.now() + timedelta(seconds=600)
        auth.state.idp_refresh_token = "refresh"
        auth._ensure_idp_token_fresh()
        mock_post.assert_not_called()

    @patch("rift.auth.requests.post")
    def test_ensure_idp_token_fresh_unset_expiration_skips_refresh(self, mock_post):
        auth = Auth(self._minimal_config)
        auth.state.idp_refresh_token = "refresh"
        auth._ensure_idp_token_fresh()
        mock_post.assert_not_called()

    @patch("rift.auth.requests.post")
    def test_ensure_idp_token_fresh_disabled_when_threshold_zero(self, mock_post):
        self._minimal_config["idp_token_refresh_threshold"] = 0
        auth = Auth(self._minimal_config)
        auth.state.idp_token_expiration = datetime.now() + timedelta(seconds=100)
        auth.state.idp_refresh_token = "refresh"
        auth._ensure_idp_token_fresh()
        mock_post.assert_not_called()

    @patch("rift.auth.requests.post")
    def test_get_idp_token_password_persists_refresh_token(self, mock_post):
        mock_post.return_value = MagicMock()
        mock_post.return_value.json.return_value = {
            "access_token": "access-1",
            "expires_in": 3600,
            "refresh_token": "refresh-1",
        }
        auth = Auth(self._minimal_config)
        with patch.dict(
            os.environ,
            {"RIFT_AUTH_USER": "user", "RIFT_AUTH_PASSWORD": "pass"},
        ):
            self.assertTrue(auth.get_idp_token())

        self.assertEqual(auth.state.idp_token, "access-1")
        self.assertEqual(auth.state.idp_refresh_token, "refresh-1")
        self.assertIsInstance(auth.state.idp_token_expiration, datetime)
        with open(self._cred_path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["idp_refresh_token"], "refresh-1")
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args[1]["data"]["grant_type"], "password")

    @patch("rift.auth.requests.post")
    def test_get_idp_token_refreshes_when_below_threshold(self, mock_post):
        mock_post.return_value = MagicMock()
        mock_post.return_value.json.return_value = {
            "access_token": "access-2",
            "expires_in": 3600,
            "refresh_token": "refresh-2",
        }
        auth = Auth(self._minimal_config)
        auth.state.idp_token = "access-old"
        auth.state.idp_refresh_token = "refresh-old"
        auth.state.idp_token_expiration = datetime.now() + timedelta(seconds=60)

        with self.assertLogs(level="INFO") as logs:
            self.assertTrue(auth.get_idp_token())
        self.assertIn(
            "retrieved existing idp_token from auth file",
            "\n".join(logs.output),
        )

        self.assertEqual(auth.state.idp_token, "access-2")
        self.assertEqual(auth.state.idp_refresh_token, "refresh-2")
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args[1]["data"]["grant_type"], "refresh_token")
        self.assertEqual(mock_post.call_args[1]["data"]["refresh_token"], "refresh-old")

    @patch("rift.auth.requests.post")
    def test_get_idp_token_skips_refresh_above_threshold(self, mock_post):
        auth = Auth(self._minimal_config)
        auth.state.idp_token = "access-ok"
        auth.state.idp_refresh_token = "refresh-ok"
        auth.state.idp_token_expiration = datetime.now() + timedelta(seconds=600)

        with self.assertLogs(level="INFO") as logs:
            self.assertTrue(auth.get_idp_token())
        self.assertIn(
            "retrieved existing idp_token from auth file",
            "\n".join(logs.output),
        )

        self.assertEqual(auth.state.idp_token, "access-ok")
        mock_post.assert_not_called()

    def test_get_idp_token_noninteractive_env_token(self):
        self._write_state({})
        auth = Auth(self._minimal_config)

        # Generate JWT token with 1 hour expiration.
        exp = int((datetime.now() + timedelta(hours=1)).timestamp())
        jwt_token = _make_jwt({"exp": exp})

        with patch.dict(os.environ, {"RIFT_AUTH_IDP_TOKEN": jwt_token}, clear=False):
            os.environ.pop("RIFT_AUTH_IDP_REFRESH_TOKEN", None)
            with self.assertLogs(level="DEBUG") as logs:
                self.assertEqual(auth.get_idp_token_noninteractive(), jwt_token)
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

    @patch("rift.auth.requests.post")
    def test_get_idp_token_noninteractive_refreshes_from_env_jwt(self, mock_post):
        mock_post.return_value = MagicMock()
        mock_post.return_value.json.return_value = {
            "access_token": "access-refreshed",
            "expires_in": 3600,
            "refresh_token": "refresh-new",
        }
        os.unlink(self._cred_path)
        auth = Auth(self._minimal_config)

        # Generate near-expiry JWT token.
        exp = int((datetime.now() + timedelta(seconds=60)).timestamp())
        jwt_token = _make_jwt({"exp": exp})

        with patch.dict(
            os.environ,
            {
                "RIFT_AUTH_IDP_TOKEN": jwt_token,
                "RIFT_AUTH_IDP_REFRESH_TOKEN": "refresh-env",
            },
        ):
            token = auth.get_idp_token_noninteractive()

        self.assertEqual(token, "access-refreshed")
        # Make sure the state in memory is updated with the new token.
        self.assertEqual(auth.state.idp_token, "access-refreshed")
        self.assertEqual(auth.state.idp_refresh_token, "refresh-new")
        self.assertFalse(auth._persist_credentials)
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args[1]["data"]["grant_type"], "refresh_token")
        self.assertEqual(mock_post.call_args[1]["data"]["refresh_token"], "refresh-env")
        # Make sure the credentials file is not created after tokens from environment
        # are refreshed.
        self.assertFalse(os.path.isfile(self._cred_path))

    @patch("rift.auth.requests.post")
    def test_get_idp_token_noninteractive_successive_calls_reuse_refreshed_env_token(
        self, mock_post
    ):
        mock_post.return_value = MagicMock()
        mock_post.return_value.json.return_value = {
            "access_token": "access-refreshed",
            "expires_in": 3600,
            "refresh_token": "refresh-new",
        }
        os.unlink(self._cred_path)
        auth = Auth(self._minimal_config)

        # Generate near-expiry JWT token.
        exp = int((datetime.now() + timedelta(seconds=60)).timestamp())
        jwt_token = _make_jwt({"exp": exp})

        with patch.dict(
            os.environ,
            {
                "RIFT_AUTH_IDP_TOKEN": jwt_token,
                "RIFT_AUTH_IDP_REFRESH_TOKEN": "refresh-env",
            },
        ):
            self.assertEqual(auth.get_idp_token_noninteractive(), "access-refreshed")
            self.assertEqual(auth.get_idp_token_noninteractive(), "access-refreshed")

        # Check the refreshed token has been requested only once.
        mock_post.assert_called_once()
        # Make sure the credentials file is not created after tokens from environment
        # are refreshed.
        self.assertFalse(os.path.isfile(self._cred_path))

    @patch("rift.auth.requests.post")
    def test_get_idp_token_noninteractive_non_jwt_env_skips_refresh(self, mock_post):
        auth = Auth(self._minimal_config)
        with patch.dict(
            os.environ,
            {
                "RIFT_AUTH_IDP_TOKEN": "opaque-token",
                "RIFT_AUTH_IDP_REFRESH_TOKEN": "refresh-env",
            },
        ):
            with self.assertLogs(level="WARNING") as logs:
                # Check opaque token from environment is returned.
                self.assertEqual(auth.get_idp_token_noninteractive(), "opaque-token")

        # Check warning is emitted because unable to extract expiration from non-JWT.
        self.assertIn(
            "unable to extract expiration from RIFT_AUTH_IDP_TOKEN",
            "\n".join(logs.output),
        )

        # Check the token has been returned without refreshing.
        mock_post.assert_not_called()

    @patch("rift.auth.requests.post")
    def test_get_idp_token_noninteractive_refreshes_from_state_file(self, mock_post):
        mock_post.return_value = MagicMock()
        mock_post.return_value.json.return_value = {
            "access_token": "access-new",
            "expires_in": 3600,
        }
        # Generate near-expiry token expiration.
        exp = (datetime.now() + timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_state(
            {
                "idp_token": "access-old",
                "idp_token_expiration": exp,
                "idp_refresh_token": "refresh-file",
            }
        )
        auth = Auth(self._minimal_config)
        with patch.dict(os.environ, {}, clear=False):
            # Ensure environment variables are not defined
            os.environ.pop("RIFT_AUTH_IDP_TOKEN", None)
            os.environ.pop("RIFT_AUTH_IDP_REFRESH_TOKEN", None)
            # Check the refreshed token is returned
            self.assertEqual(auth.get_idp_token_noninteractive(), "access-new")

        # Check new token has been requested with refresh token from state file.
        mock_post.assert_called_once()
        self.assertEqual(
            mock_post.call_args[1]["data"]["refresh_token"], "refresh-file"
        )
