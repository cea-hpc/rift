#
# Copyright (C) 2026 CEA
#

import os
from unittest.mock import Mock, call, patch

from rift.annex.server import ServerAnnex

from ..TestUtils import RiftTestCase, make_temp_filename


class ServerAnnexTest(RiftTestCase):
    """Tests for ServerAnnex HTTP annex with optional IDP token auth."""

    _CONFIG = {'idp_app_token': 'app-token', 's3_credential_file': '/tmp/creds'}
    _ANNEX_URL = 'https://annex.example.com/objects'

    def _mock_response(self, content=b'data'):
        res = Mock()
        res.status_code = 200
        res.raw = Mock()
        res.raw.read = Mock(side_effect=[content, b''])
        res.iter_content = Mock(return_value=[content])
        res.__bool__ = Mock(return_value=True)
        return res

    @patch('rift.annex.server.requests.get')
    def test_get_no_auth(self, mock_get):
        """get() sends no Authorization header when auth is not configured."""
        mock_get.return_value = self._mock_response()
        annex = ServerAnnex({}, self._ANNEX_URL)
        dest = make_temp_filename()
        self.assertTrue(annex.get('ABCDEF', dest))
        mock_get.assert_called_once_with(
            f'{self._ANNEX_URL}/ABCDEF',
            stream=True,
            timeout=15,
            headers={},
        )
        os.remove(dest)

    @patch('rift.annex.server.Auth')
    @patch('rift.annex.server.requests.get')
    def test_get_idp_token_bearer(self, mock_get, mock_auth_cls):
        """get() sends Bearer token when auth is idp_token."""
        mock_auth_cls.return_value.get_idp_token_noninteractive.return_value = (
            'test-idp-token'
        )
        mock_get.return_value = self._mock_response()
        annex = ServerAnnex(self._CONFIG, self._ANNEX_URL, auth='idp_token')
        dest = make_temp_filename()
        self.assertTrue(annex.get('ABCDEF', dest))
        mock_auth_cls.return_value.get_idp_token_noninteractive.assert_called_once()
        mock_get.assert_called_once_with(
            f'{self._ANNEX_URL}/ABCDEF',
            stream=True,
            timeout=15,
            headers={'Authorization': 'Bearer test-idp-token'},
        )
        os.remove(dest)

    @patch('rift.annex.server.Auth')
    @patch('rift.annex.server.requests.get')
    def test_backup_idp_token_bearer(self, mock_get, mock_auth_cls):
        """backup() sends Bearer token on annex fetches when auth is idp_token."""
        mock_auth_cls.return_value.get_idp_token_noninteractive.return_value = (
            'test-idp-token'
        )
        mock_get.return_value = self._mock_response()

        digest = 'ABCDEF'
        pointer_file = make_temp_filename()
        with open(pointer_file, 'w', encoding='utf-8') as fh:
            fh.write(digest)

        annex = ServerAnnex(self._CONFIG, self._ANNEX_URL, auth='idp_token')
        output = make_temp_filename()
        annex.backup([pointer_file], output)

        expected_headers = {'Authorization': 'Bearer test-idp-token'}
        mock_get.assert_has_calls(
            [
                call(
                    f'{self._ANNEX_URL}/{digest}',
                    stream=True,
                    timeout=15,
                    headers=expected_headers,
                ),
                call(
                    f'{self._ANNEX_URL}/{digest}.info',
                    stream=True,
                    timeout=15,
                    headers=expected_headers,
                ),
            ],
            any_order=True,
        )
        os.remove(pointer_file)
        os.remove(output)
