import unittest

from app.core.proxy import parse_proxy_url


class ParseProxyUrlTests(unittest.TestCase):
    def test_socks5_url(self):
        self.assertEqual(
            parse_proxy_url("socks5://127.0.0.1:7890"),
            {"proxy_type": "socks5", "addr": "127.0.0.1", "port": 7890, "rdns": True},
        )

    def test_http_url(self):
        self.assertEqual(
            parse_proxy_url("http://127.0.0.1:8080"),
            {"proxy_type": "http", "addr": "127.0.0.1", "port": 8080, "rdns": True},
        )

    def test_https_is_treated_as_http_connect(self):
        parsed = parse_proxy_url("https://127.0.0.1:8080")
        self.assertEqual(parsed["proxy_type"], "http")

    def test_bare_host_port_defaults_to_socks5(self):
        parsed = parse_proxy_url("127.0.0.1:7890")
        self.assertEqual(parsed["proxy_type"], "socks5")
        self.assertEqual(parsed["port"], 7890)

    def test_port_defaults_when_omitted(self):
        self.assertEqual(parse_proxy_url("socks5://127.0.0.1")["port"], 7890)

    def test_credentials_are_kept(self):
        parsed = parse_proxy_url("socks5://user:secret@10.0.0.1:1080")
        self.assertEqual(parsed["addr"], "10.0.0.1")
        self.assertEqual(parsed["port"], 1080)
        self.assertEqual(parsed["username"], "user")
        self.assertEqual(parsed["password"], "secret")

    def test_blank_means_direct_connection(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertIsNone(parse_proxy_url(value))

    def test_unknown_scheme_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_proxy_url("ftp://127.0.0.1:21")

    def test_missing_host_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_proxy_url("socks5://")


if __name__ == "__main__":
    unittest.main()
