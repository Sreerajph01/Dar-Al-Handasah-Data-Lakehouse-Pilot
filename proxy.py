import socket
import threading

def handle_client(client_socket):
    target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    target_socket.connect(("dar-seaweedfs-s3", 8333))
    
    def forward(src, dst, name):
        try:
            while True:
                data = src.recv(4096)
                if not data:
                    break
                if name == "req":
                    print("--- REQUEST ---")
                    print(data.decode('utf-8', errors='replace'))
                elif name == "res":
                    print("--- RESPONSE ---")
                    print(data.decode('utf-8', errors='replace'))
                dst.sendall(data)
        except Exception as e:
            print(f"Error {name}: {e}")
        finally:
            src.close()
            dst.close()
            
    t1 = threading.Thread(target=forward, args=(client_socket, target_socket, "req"))
    t2 = threading.Thread(target=forward, args=(target_socket, client_socket, "res"))
    t1.start()
    t2.start()

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(("0.0.0.0", 9999))
server.listen(5)
print("Proxy listening on 9999...")

while True:
    client, addr = server.accept()
    threading.Thread(target=handle_client, args=(client,)).start()
