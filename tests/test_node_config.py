import tempfile
import unittest
from pathlib import Path

from genesis.node.config import load_config


class NodeConfigTests(unittest.TestCase):
    def test_load_config_defaults_to_local_bootstrap_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_config(tmpdir)

            self.assertTrue(config.network.allow_local_bootstrap)

    def test_load_config_supports_webrtc_ice_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(
                """
network:
  webrtc_enabled: false
  stun_servers:
    - "stun:stun1.example.net:3478"
  turn_servers:
    - urls:
        - "turn:turn.example.net:3478?transport=udp"
        - "turns:turn.example.net:5349?transport=tcp"
      username: "relay-user"
      credential: "relay-pass"
  webrtc_offer_timeout: 18
  webrtc_session_ttl: 240
""".strip(),
                encoding="utf-8",
            )

            config = load_config(tmpdir)

            self.assertFalse(config.network.webrtc_enabled)
            self.assertEqual(config.network.stun_servers, ["stun:stun1.example.net:3478"])
            self.assertEqual(
                config.network.turn_servers,
                [
                    {
                        "urls": [
                            "turn:turn.example.net:3478?transport=udp",
                            "turns:turn.example.net:5349?transport=tcp",
                        ],
                        "username": "relay-user",
                        "credential": "relay-pass",
                    }
                ],
            )
            self.assertEqual(config.network.webrtc_offer_timeout, 18)
            self.assertEqual(config.network.webrtc_session_ttl, 240)


if __name__ == "__main__":
    unittest.main()
