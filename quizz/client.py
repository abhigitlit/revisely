import socket


socket = socket.socket()
socket.connect(('127.0.0.1', 5995))
msg = input()
while True:
    socket.send(msg.encode())
    msg = input()