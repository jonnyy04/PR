from flask import Flask, request, jsonify
import os
import logging
from threading import Lock

app = Flask(__name__)
logging.basicConfig(level=logging.WARNING)  # Reduce logging overhead
logger = logging.getLogger(__name__)

FOLLOWER_ID = os.getenv('FOLLOWER_ID', 'unknown')

data_store = {}
store_lock = Lock()

logger.warning(f"Follower {FOLLOWER_ID} started")

@app.route('/replicate', methods=['POST'])
def replicate():
    data = request.json
    if not data or 'key' not in data or 'value' not in data:
        return jsonify({"error": "Missing key or value"}), 400
    
    key = data['key']
    value = data['value']
    
    with store_lock:
        data_store[key] = value
    
    return jsonify({"status": "success"}), 200

@app.route('/read', methods=['GET'])
def read():
    key = request.args.get('key')
    if not key:
        return jsonify({"error": "Missing key parameter"}), 400
    
    with store_lock:
        if key in data_store:
            return jsonify({
                "key": key,
                "value": data_store[key],
                "follower_id": FOLLOWER_ID
            }), 200
        else:
            return jsonify({"error": "Key not found"}), 404

@app.route('/dump', methods=['GET'])
def dump():
    with store_lock:
        return jsonify({
            "data": dict(data_store),
            "count": len(data_store),
            "follower_id": FOLLOWER_ID
        }), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "role": "follower",
        "follower_id": FOLLOWER_ID
    }), 200

@app.route('/reset', methods=['POST'])
def reset():
    with store_lock:
        data_store.clear()
    return jsonify({"status": "cleared", "role": "follower", "follower_id": FOLLOWER_ID}), 200


if __name__ == '__main__':
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    app.run(host='0.0.0.0', port=5000, threaded=True, processes=1)