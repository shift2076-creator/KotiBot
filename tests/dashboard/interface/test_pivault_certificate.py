import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from subsystems.network.pivault_certificate import (
    DOWNLOAD_ROUTE,
    STATUS_ROUTE,
    read_certificate,
    register_pivault_certificate_routes,
)
from subsystems.security.security_routes import request_policy


def make_certificate(directory):
    key = Path(directory, "key.pem")
    cert = Path(directory, "root.crt")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(cert), "-days", "2",
         "-subj", "/CN=Test Root"],
        check=True, capture_output=True,
    )
    return cert


def client_for(path):
    app = Flask(__name__)
    register_pivault_certificate_routes(app, {"path": path})
    return app.test_client()


class PivaultCertificateTests(unittest.TestCase):
    def test_reports_fingerprint_and_serves_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            cert = make_certificate(directory)
            client = client_for(str(cert))

            status = client.get(STATUS_ROUTE).get_json()
            self.assertTrue(status["ready"])
            self.assertRegex(status["fingerprint"], r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$")

            response = client.get(DOWNLOAD_ROUTE)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, cert.read_bytes())
            self.assertIn('filename="pivault-root.crt"', response.headers["Content-Disposition"])
            self.assertEqual(response.mimetype, "application/x-x509-ca-cert")

    def test_missing_unset_or_bad_file_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            junk = Path(directory, "junk.crt")
            junk.write_text("not a certificate")
            big = Path(directory, "big.crt")
            big.write_bytes(b"x" * 70000)

            for path in ("", str(Path(directory, "absent.crt")), str(junk), str(big)):
                client = client_for(path)
                self.assertEqual(client.get(STATUS_ROUTE).get_json(),
                                 {"ok": True, "ready": False, "fingerprint": ""}, path)
                self.assertEqual(client.get(DOWNLOAD_ROUTE).status_code, 404, path)

    def test_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            cert = make_certificate(directory)
            link = Path(directory, "link.crt")
            os.symlink(cert, link)
            self.assertIsNone(read_certificate(str(link)))

    def test_routes_need_the_dashboard_login(self):
        self.assertEqual(request_policy("GET", STATUS_ROUTE), "dashboard")
        self.assertEqual(request_policy("GET", DOWNLOAD_ROUTE), "dashboard")


if __name__ == "__main__":
    unittest.main()
