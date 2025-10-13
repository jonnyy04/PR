import socket
import os
import sys
from urllib.parse import unquote


MIME_TYPES_MAP = {
    '.html': 'text/html',
    '.png': 'image/png',
    '.pdf': 'application/pdf',
}


def get_mime_type(file_path):
    _, ext = os.path.splitext(file_path.lower())
    return MIME_TYPES_MAP.get(ext)

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
        <tr><th>Name</th><th>Type</th></tr>
"""
    if relative_path != '/':
        html += f'<tr><td><a href="../">..</a></td><td>[DIR]</td></tr>'
        
    for item in items:
        full_path = os.path.join(path, item)
        url_path = os.path.join(relative_path, item).replace('\\', '/')
        
        if os.path.isdir(full_path):
            display_name = f'<b>{item}/</b>'
            item_type = '[DIR]'
            url_path += '/'
        else:
            display_name = item
            item_type = '[FILE]'

        html += f'<tr><td><a href="{url_path}">{display_name}</a></td><td>{item_type}</td></tr>'

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

def handle_request(client_socket, served_dir):
    try:
        request = client_socket.recv(4096).decode('utf-8')
        if not request:
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
        
        if os.path.isdir(file_path):
            if not relative_path.endswith('/') and relative_path:
                header = f"HTTP/1.1 301 Moved Permanently\r\nLocation: /{relative_path}/\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                client_socket.sendall(header.encode('utf-8'))
                return

            relative_path_for_listing = '/' + relative_path
            body = generate_directory_listing(file_path, relative_path_for_listing)
            header = build_response_header(200, "OK", "text/html", len(body))
            client_socket.sendall(header + body)
            print(f"Served directory listing for: /{relative_path}")
            return

        if os.path.exists(file_path) and os.path.isfile(file_path):
            mime_type = get_mime_type(file_path)
            
            if mime_type is None:
                send_error(client_socket, 404, "Not Found", f"Unknown file type for {relative_path}")
                return

            with open(file_path, 'rb') as f:
                content = f.read()
                
            header = build_response_header(200, "OK", mime_type, len(content))
            client_socket.sendall(header)
            client_socket.sendall(content)
            print(f"Served file: /{relative_path} ({mime_type})")

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

def run_server(served_dir, port):
    
    if not os.path.isdir(served_dir):
        print(f"Error: Directory '{served_dir}' does not exist.")
        sys.exit(1)
        
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(('', port))
        server_socket.listen(1)
        print(f"[*] Server listening on port {port} and serving directory: {served_dir}")
        print(f"[*] Access it at http://localhost:{port}/index.html")

        while True:
            client_conn, client_addr = server_socket.accept()
            print(f"[*] Accepted connection from {client_addr[0]}:{client_addr[1]}")
            handle_request(client_conn, served_dir)
            
    except KeyboardInterrupt:
        print("\n[*] Server shutting down...")
    except Exception as e:
        print(f"\n[*] Server crashed: {e}")
    finally:
        server_socket.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <directory_to_serve> <port>")
        sys.exit(1)
    
    served_dir = sys.argv[1]
    try:
        port = int(sys.argv[2])
    except ValueError:
        print("Error: Port must be an integer.")
        sys.exit(1)

    run_server(served_dir, port)