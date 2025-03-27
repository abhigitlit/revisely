import socket


socket = socket.socket()
socket.bind(('127.0.0.1', 5995))
socket.listen()
new_socket = socket.accept()[0]
msg = new_socket.recv(1024)
while True:
    print(msg.decode())
    msg = new_socket.recv(2)
    print(len(msg))

    print(msg.decode()=="quit")
    
new_socket.close()