import requests

SSE_SERVER_URL = "http://localhost:5000/notify"

def notify_sse(message: str):
    """Sends a status update to the SSE server."""
    try:
        # Use a short timeout for non-blocking notification
        # Increased timeout slightly from 1 to 2 for robustness
        requests.post(SSE_SERVER_URL, json={'message': message}, timeout=2)
        print(f"[SSE Notify] Sent: {message}")
    except requests.exceptions.RequestException as e:
        print(f"[SSE Notify] Failed to send update '{message}': {type(e).__name__} - {e}")
    except Exception as e:
        print(f"[SSE Notify] An unexpected error occurred sending '{message}': {type(e).__name__} - {e}")
