from flask import Flask, Response, request, jsonify
import time
import queue

app = Flask(__name__)

# Use a thread-safe queue to hold messages
message_queue = queue.Queue()

@app.route('/events')
def sse():
    def generate():
        # Send an initial connection message
        yield "event: connection\ndata: Connected to SSE server\n\n"
        while True:
            try:
                # Wait for a message from the queue (with timeout)
                message = message_queue.get(timeout=60) # Timeout after 60s of inactivity
                print(f"[SSE Generate] Sending: {message}")
                # Send message as 'update' event
                yield f"event: update\ndata: {message}\n\n"
                message_queue.task_done()
            except queue.Empty:
                # Send a keep-alive comment if no message for a while
                yield ": keep-alive\n\n"
                time.sleep(10) # Wait before checking again
            except Exception as e:
                print(f"[SSE Generate] Error: {e}")
                yield f"event: error\ndata: Server error: {e}\n\n"
                break # Exit loop on error

    return Response(generate(), mimetype='text/event-stream')

@app.route('/notify', methods=['POST'])
def notify():
    """Endpoint for other processes to send status updates."""
    data = request.get_json()
    if data and 'message' in data:
        message = data['message']
        print(f"[SSE Notify Endpoint] Received: {message}")
        message_queue.put(message) # Add message to the queue
        return jsonify({"status": "Message received"}), 200
    else:
        return jsonify({"status": "Invalid payload", "error": "Missing 'message' key"}), 400

if __name__ == "__main__":
    # Use 0.0.0.0 to make it accessible on the network if needed
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
