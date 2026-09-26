import unittest

from app.core.proxy import parse_proxy_url


class ParseProxyUrlTests(unittest.TestCase):
    def test_socks5_url(self):
        self.assertEqual(
            parse_proxy_url("socks5://127.0.0.1:7890"),
            ("socks5", "127.0.0.1", 7890, True, None, None),
        )

    def test_http_url(self):
        self.assertEqual(
            parse_proxy_url("http://127.0.0.1:8080"),
            ("http", "127.0.0.1", 8080, True, None, None),
        )

    def test_https_is_treated_as_http_connect(self):
        parsed = parse_proxy_url("https://127.0.0.1:8080")
        self.assertEqual(parsed[0], "http")

    def test_bare_host_port_defaults_to_socks5(self):
        parsed = parse_proxy_url("127.0.0.1:7890")
        self.assertEqual(parsed[0], "socks5")
        self.assertEqual(parsed[2], 7890)

    def test_port_defaults_when_omitted(self):
        self.assertEqual(parse_proxy_url("socks5://127.0.0.1")[2], 7890)

    def test_credentials_are_kept(self):
        parsed = parse_proxy_url("socks5://user:secret@10.0.0.1:1080")
        self.assertEqual(parsed[1], "10.0.0.1")
        self.assertEqual(parsed[2], 1080)
        self.assertEqual(parsed[4], "user")
        self.assertEqual(parsed[5], "secret")

    def test_tuple_supports_script_style_indexing(self):
        # persistent_chat_demo.py 用 PROXY[1] / PROXY[2] 打印主机和端口，
        # 所以这里必须是元组而不是 dict（换成 dict 会 KeyError: 1）。
        parsed = parse_proxy_url("socks5://127.0.0.1:7890")
        self.assertEqual((parsed[1], parsed[2]), ("127.0.0.1", 7890))

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
