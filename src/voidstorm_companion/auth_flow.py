import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import keyring

SERVICE_NAME = "voidstorm-companion"
ACCOUNT_NAME = "api-token"
LOCAL_PORT = 9473


def get_stored_token() -> str | None:
    return keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)


def store_token(token: str):
    keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, token)


def clear_token():
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except keyring.errors.PasswordDeleteError:
        pass


def authenticate(api_url: str, timeout: int = 120) -> str | None:
    token_result: list[str | None] = [None]

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/callback":
                params = parse_qs(parsed.query)
                token = params.get("token", [None])[0]
                if token:
                    token_result[0] = token
                    store_token(token)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body><h2>Authenticated!</h2>"
                        b"<p>You can close this tab and return to Voidstorm Companion.</p>"
                        b"</body></html>"
                    )
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing token parameter")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", LOCAL_PORT), CallbackHandler)
    server.timeout = timeout

    redirect_url = f"http://localhost:{LOCAL_PORT}/callback"
    auth_url = f"{api_url}/api/companion/auth?redirect={redirect_url}"
    webbrowser.open(auth_url)

    server.handle_request()
    server.server_close()

    return token_result[0]
