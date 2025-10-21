import socket
import os
import sys
from urllib.parse import unquote
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
import time
from collections import defaultdict, deque


MIME_TYPES_MAP = {
    '.html': 'text/html',
    '.png': 'image/png',
    '.pdf': 'application/pdf',
}

file_access_counter = defaultdict(int)
counter_lock = Lock()

rate_limit_data = defaultdict(lambda: deque())
rate_limit_lock = Lock()
RATE_LIMIT = 10 # requests per second
RATE_WINDOW = 1.0  # seconds


def get_mime_type(file_path):
    _, ext = os.path.splitext(file_path.lower())
    return MIME_TYPES_MAP.get(ext)


def check_rate_limit(client_ip):
    
    with rate_limit_lock:
        current_time = time.time()
        request_times = rate_limit_data[client_ip]
        
        # mai vechi de 1 secunda
        while request_times and current_time - request_times[0] > RATE_WINDOW:
            request_times.popleft()
        
        if len(request_times) >= RATE_LIMIT:
            return False
        
        request_times.append(current_time)
        return True


def increment_counter_naive(file_path):
    
    global file_access_counter
    
    current_count = file_access_counter[file_path]
    
    #  race condition artificial
    time.sleep(0.001)
    
    file_access_counter[file_path] = current_count + 1


def increment_counter_safe(file_path):
    
    with counter_lock:
        file_access_counter[file_path] += 1


def generate_directory_listing(path, relative_path):
    items = sorted(os.listdir(path))
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Index of {relative_path}</title>
    <style>
        body {{ font-family: sans-serif; }}
        table {{ width: 80%; border-collapse: collapse; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
    </style>
</head>
<body>
    <h1>Index of {relative_path}</h1>
    <table>
        <tr><th>Name</th><th>Type</th><th>Access Count</th></tr>
"""
    if relative_path != '/':
        html += f'<tr><td><a href="../">..</a></td><td>[DIR]</td><td>-</td></tr>'
        
    for item in items:
        full_path = os.path.join(path, item)
        url_path = os.path.join(relative_path, item).replace('\\', '/')
        
        if os.path.isdir(full_path):
            display_name = f'<b>{item}/</b>'
            item_type = '[DIR]'
            url_path += '/'
            access_count = '-'
        else:
            display_name = item
            item_type = '[FILE]'
            file_key = os.path.join(relative_path, item)
            access_count = file_access_counter.get(file_key, 0)

        html += f'<tr><td><a href="{url_path}">{display_name}</a></td><td>{item_type}</td><td>{access_count}</td></tr>'

    html += """
    </table>
</body>
</html>
"""
    return html.encode('utf-8')


def build_response_header(status_code, status_text, content_type, content_length):
    header = f"HTTP/1.1 {status_code} {status_text}\r\n"
    header += f"Content-Type: {content_type}\r\n"
    header += f"Content-Length: {content_length}\r\n"
    header += "Connection: close\r\n" 
    header += "\r\n"
    return header.encode('utf-8')


def handle_request(client_socket, served_dir, client_addr, use_safe_counter=True):
    try:
        request = client_socket.recv(4096).decode('utf-8')
        if not request:
            return
        
        client_ip = client_addr[0]
        if not check_rate_limit(client_ip):
            print(f"[!] Rate limit exceeded for {client_ip}")
            send_error(client_socket, 429, "Too Many Requests", 
                      "Rate limit exceeded. Please try again later.")
            return

        first_line = request.split('\n')[0].strip()
        parts = first_line.split()

        if len(parts) < 3 or parts[0] != 'GET':
            print(f"Invalid request: {first_line}")
            send_error(client_socket, 400, "Bad Request")
            return

        relative_path = unquote(parts[1])
        if relative_path.startswith('/'):
            relative_path = relative_path[1:]

        if '..' in relative_path or relative_path.startswith('/'):
            send_error(client_socket, 403, "Forbidden")
            return

        file_path = os.path.join(served_dir, relative_path)
        

        time.sleep(1)

        
        if os.path.isdir(file_path):
            if not relative_path.endswith('/') and relative_path:
                header = f"HTTP/1.1 301 Moved Permanently\r\nLocation: /{relative_path}/\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                client_socket.sendall(header.encode('utf-8'))
                return

            relative_path_for_listing = '/' + relative_path
            body = generate_directory_listing(file_path, relative_path_for_listing)
            header = build_response_header(200, "OK", "text/html", len(body))
            client_socket.sendall(header + body)
            print(f"Served directory listing for: /{relative_path} from {client_ip}")
            return

        if os.path.exists(file_path) and os.path.isfile(file_path):
            mime_type = get_mime_type(file_path)
            
            if mime_type is None:
                send_error(client_socket, 404, "Not Found", 
                          f"Unknown file type for {relative_path}")
                return

            file_key = '/' + relative_path
            if use_safe_counter:
                increment_counter_safe(file_key)
            else:
                increment_counter_naive(file_key)

            with open(file_path, 'rb') as f:
                content = f.read()
                
            header = build_response_header(200, "OK", mime_type, len(content))
            client_socket.sendall(header)
            client_socket.sendall(content)
            print(f"Served file: /{relative_path} ({mime_type}) to {client_ip}")

        else:
            send_error(client_socket, 404, "Not Found")

    except Exception as e:
        print(f"An error occurred: {e}")
        send_error(client_socket, 500, "Internal Server Error")
    finally:
        client_socket.close()


def send_error(client_socket, status_code, status_text, message=""):
    error_html = f"<html><body><h1>{status_code} {status_text}</h1><p>{message}</p></body></html>".encode('utf-8')
    header = build_response_header(status_code, status_text, "text/html", len(error_html))
    client_socket.sendall(header + error_html)


def run_server(served_dir, port, max_workers=10, use_safe_counter=True):
    
    if not os.path.isdir(served_dir):
        print(f"Error: Directory '{served_dir}' does not exist.")
        sys.exit(1)
        
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(('', port))
        server_socket.listen(5)
        
        counter_mode = "Thread-safe" if use_safe_counter else "Naive (race condition)"
        print(f"[*] Concurrent server listening on port {port}")
        print(f"[*] Serving directory: {served_dir}")
        print(f"[*] Thread pool size: {max_workers}")
        print(f"[*] Counter mode: {counter_mode}")
        print(f"[*] Rate limit: {RATE_LIMIT} requests/second per IP")
        print(f"[*] Access it at http://localhost:{port}/")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            while True:
                client_conn, client_addr = server_socket.accept()
                print(f"[*] Accepted connection from {client_addr[0]}:{client_addr[1]}")
                
                executor.submit(handle_request, client_conn, served_dir, 
                              client_addr, use_safe_counter)
            
    except KeyboardInterrupt:
        print("\n[*] Server shutting down...")
    except Exception as e:
        print(f"\n[*] Server crashed: {e}")
    finally:
        server_socket.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <directory_to_serve> <port> [max_workers] [--naive-counter]")
        print(f"  max_workers: optional, default 10")
        print(f"  --naive-counter: optional, use naive counter (for demonstrating race condition)")
        sys.exit(1)
    
    served_dir = sys.argv[1]
    
    try:
        port = int(sys.argv[2])
    except ValueError:
        print("Error: Port must be an integer.")
        sys.exit(1)
    
    max_workers = 20
    if len(sys.argv) >= 4 and sys.argv[3].isdigit():
        max_workers = int(sys.argv[3])
    
    use_safe_counter = '--naive-counter' not in sys.argv
    
    run_server(served_dir, port, max_workers, use_safe_counter)