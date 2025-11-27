from flask import Flask, request, jsonify

import asyncio
import aiohttp
import random
import time
import os
import logging
from threading import Lock, Thread
from concurrent.futures import Future

app = Flask(__name__)
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

WRITE_QUORUM = int(os.getenv('WRITE_QUORUM', '3'))
MIN_DELAY = float(os.getenv('MIN_DELAY', '0.0001'))
MAX_DELAY = float(os.getenv('MAX_DELAY', '0.001'))
FOLLOWERS = [f.strip() for f in os.getenv('FOLLOWERS', '').split(',') if f.strip()]

data_store = {}
store_lock = Lock()

logger.warning(f"Leader started with WRITE_QUORUM={WRITE_QUORUM}, followers={len(FOLLOWERS)}")

#  GLOBAL EVENT LOOP RUNNING IN BACKGROUND THREAD
loop = asyncio.new_event_loop()

def loop_thread():
    asyncio.set_event_loop(loop)
    loop.run_forever()

thread = Thread(target=loop_thread, daemon=True)
thread.start()

#  ASYNC REPLICATION LOGIC
async def replicate_to_follower(follower_url, key, value, delay):
    try:
        await asyncio.sleep(delay)

        timeout = aiohttp.ClientTimeout(total=5, connect=2)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.post(
                f"{follower_url}/replicate",
                json={"key": key, "value": value}
            ) as response:
                return response.status == 200
    except Exception as e:
        logger.warning(f"Replication error to {follower_url}: {e}")
        return False


async def replicate_to_followers(key, value):
    if not FOLLOWERS:
        return True

    if WRITE_QUORUM > len(FOLLOWERS):
        logger.error("Quorum > number of followers")
        return False

    tasks = []
    for follower_url in FOLLOWERS:
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        tasks.append(asyncio.create_task(
            replicate_to_follower(follower_url, key, value, delay)
        ))

    successful = 0

    for completed in asyncio.as_completed(tasks):
        result = await completed
        if result:
            successful += 1

        if successful >= WRITE_QUORUM:
            logger.info(f"QUORUM met early {successful}/{len(FOLLOWERS)}")
            return True

    logger.warning(f"QUORUM NOT reached {successful}/{len(FOLLOWERS)}")
    return False


#  SYNC CALLER TO ASYNC LOOP
def run_replication(key, value):
    """
    This submits the coroutine to the GLOBAL async loop
    and waits for QUORUM result — but does NOT kill remaining tasks.
    """
    future: Future = asyncio.run_coroutine_threadsafe(
        replicate_to_followers(key, value),
        loop
    )
    return future.result()  # blocking only for QUORUM


#  FLASK ROUTES
@app.route('/write', methods=['POST'])
def write():
    start_time = time.perf_counter()

    data = request.json
    if not data or 'key' not in data or 'value' not in data:
        return jsonify({"error": "Missing key or value"}), 400

    key = data['key']
    value = data['value']

    with store_lock:
        data_store[key] = value

    quorum_reached = run_replication(key, value)

    elapsed = time.perf_counter() - start_time

    if quorum_reached:
        return jsonify({
            "status": "success",
            "key": key,
            "latency": elapsed
        }), 200
    else:
        return jsonify({
            "status": "quorum_not_reached",
            "message": "Not enough followers confirmed"
        }), 503


@app.route('/read', methods=['GET'])
def read():
    key = request.args.get('key')
    if not key:
        return jsonify({"error": "Missing key parameter"}), 400

    with store_lock:
        if key in data_store:
            return jsonify({"key": key, "value": data_store[key]}), 200
        else:
            return jsonify({"error": "Key not found"}), 404


@app.route('/dump', methods=['GET'])
def dump():
    with store_lock:
        return jsonify({"data": dict(data_store), "count": len(data_store)}), 200


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "role": "leader", "quorum": WRITE_QUORUM}), 200


@app.route('/reset', methods=['POST'])
def reset():
    with store_lock:
        data_store.clear()
    return jsonify({"status": "cleared", "role": "leader"}), 200


##################################################

if __name__ == '__main__':
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    app.run(host='0.0.0.0', port=5000, threaded=True, processes=1)
