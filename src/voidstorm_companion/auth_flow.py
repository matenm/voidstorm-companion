import webbrowser
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
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
    expected_state = secrets.token_urlsafe(32)

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/callback":
                params = parse_qs(parsed.query)
                token = params.get("token", [None])[0]
                state = params.get("state", [None])[0]
                if state != expected_state:
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Invalid state parameter")
                elif token:
                    token_result[0] = token
                    store_token(token)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        b"<!DOCTYPE html><html><head><meta charset='utf-8'>"
                        b"<title>Voidstorm Companion</title>"
                        b"<script>history.replaceState(null,'','/');</script>"
                        b"<style>"
                        b"body{margin:0;min-height:100vh;display:flex;align-items:center;"
                        b"justify-content:center;background:#0a0a1a;color:#e2e8f0;"
                        b"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}"
                        b".card{text-align:center;padding:3rem;border-radius:1rem;"
                        b"background:linear-gradient(135deg,#1a1a2e,#16213e);"
                        b"border:1px solid rgba(124,58,237,0.3);max-width:400px;}"
                        b"h2{color:#a78bfa;margin:0 0 0.5rem;font-size:1.5rem;}"
                        b"p{color:#94a3b8;margin:0;font-size:0.95rem;}"
                        b".hint{color:#64748b;margin-top:1rem;font-size:0.8rem;}"
                        b".dot{width:12px;height:12px;background:#22c55e;border-radius:50%;"
                        b"display:inline-block;margin-right:8px;}"
                        b"</style></head><body><div class='card'>"
                        b"<h2><span class='dot'></span>Authenticated</h2>"
                        b"<p>You can close this tab and return to Voidstorm Companion.</p>"
                        b"<p class='hint'>This is your local Voidstorm Companion app.</p>"
                        b"</div></body></html>"
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
    params = urlencode({"redirect": redirect_url, "state": expected_state})
    auth_url = f"{api_url}/api/companion/auth?{params}"
    webbrowser.open(auth_url)

    server.handle_request()
    server.server_close()

    return token_result[0]
