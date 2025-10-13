import socket
import sys
import os
from urllib.parse import urlparse

def run_client(host, port, path, save_dir):
    
    if not os.path.isdir(save_dir):
        print(f"Error: Save directory '{save_dir}' does not exist.")
        sys.exit(1)

    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"[*] Connecting to {host}:{port}...")
        client_socket.connect((host, port))

        request = f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n"
        client_socket.sendall(request.encode('utf-8'))

        response_data = b''
        while True:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            response_data += chunk
            
        if not response_data:
            print("[!] Empty response received.")
            return

        header_end = response_data.find(b'\r\n\r\n')
        if header_end == -1:
            print("[!] Invalid HTTP response (no header end).")
            return
            
        header = response_data[:header_end].decode('utf-8', errors='ignore')
        body = response_data[header_end + 4:]
        
        status_line = header.split('\r\n')[0]
        print(f"\n<<< HTTP Response Status: {status_line} >>>")
        if not status_line.startswith("HTTP/1.1 200 OK"):
            print(f"\n--- Response Body ---\n{body.decode('utf-8', errors='ignore')}\n---------------------")
            return

        content_type = ""
        for line in header.split('\r\n'):
            if line.lower().startswith('content-type:'):
                content_type = line.split(':')[1].strip().split(';')[0]
                break
        
        if 'text/html' in content_type.lower():
            print(f"\n--- HTML Content for {path} ---\n{body.decode('utf-8', errors='ignore')}\n----------------------------------")
        elif 'image/png' in content_type.lower() or 'application/pdf' in content_type.lower():
            filename = os.path.basename(path)
            if not filename:
                print(f"[!] Cannot save a directory listing as a file. Displaying content instead.")
                print(f"\n--- Directory Content ---\n{body.decode('utf-8', errors='ignore')}\n--------------------------")
                return
                
            save_path = os.path.join(save_dir, filename)
            with open(save_path, 'wb') as f:
                f.write(body)
            print(f"[SUCCESS] File saved: {save_path} ({len(body)} bytes)")
        else:
            print(f"[WARNING] Unknown Content-Type ({content_type}). Displaying raw content.")
            print(f"\n--- RAW Content ---\n{body}\n-------------------")

    except ConnectionRefusedError:
        print(f"[ERROR] Connection refused. Is the server running on {host}:{port}?")
    except socket.gaierror:
        print(f"[ERROR] Hostname resolution error for {host}")
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}")
    finally:
        client_socket.close()
        print("[*] Connection closed.")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(f"Usage: python {sys.argv[0]} <server_host> <server_port> <url_path> <directory_to_save>")
        sys.exit(1)
        
    server_host = sys.argv[1]
    try:
        server_port = int(sys.argv[2])
    except ValueError:
        print("Error: Server port must be an integer.")
        sys.exit(1)
        
    url_path = sys.argv[3]
    directory = sys.argv[4]

    run_client(server_host, server_port, url_path, directory)