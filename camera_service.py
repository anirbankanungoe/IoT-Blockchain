import socket
import json
import cv2
import time
import requests
from datetime import datetime
import threading
import os
import io
import subprocess
import sys
import struct

print("Starting Camera Service...")
sys.stdout.flush()

class CameraService:
    def __init__(self):
        print("Initializing Camera Service...")
        sys.stdout.flush()
        
        # Get configuration from environment variables with defaults
        self.rpi_zerotier_ip = os.getenv('RPI_ZEROTIER_IP', '172.23.228.240')
        self.windows_zerotier_ip = os.getenv('WINDOWS_ZEROTIER_IP', '172.23.67.130')
        self.host = '0.0.0.0'  # Listen on all interfaces
        self.port = int(os.getenv('SERVICE_PORT', '5555'))
        self.camera = None
        self.capture_thread = None
        self.stop_capture = False
        
        print(f"Configuration loaded:")
        print(f"RPI ZeroTier IP: {self.rpi_zerotier_ip}")
        print(f"Windows ZeroTier IP: {self.windows_zerotier_ip}")
        print(f"Listening on: {self.host}:{self.port}")
        sys.stdout.flush()

    def init_camera(self):
        """Initialize the camera device"""
        try:
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                raise Exception("Could not open camera")
            print("Camera initialized successfully")
            sys.stdout.flush()
            return True
        except Exception as e:
            print(f"Error initializing camera: {str(e)}")
            sys.stdout.flush()
            return False

    def capture_and_send(self, client_socket, request_id):
        """Capture images and send them to the client"""
        try:
            if not self.init_camera():
                return
            
            start_time = time.time()
            image_count = 0
            
            while time.time() - start_time < 120 and not self.stop_capture:  # 2 minutes
                # Capture frame
                ret, frame = self.camera.read()
                if not ret:
                    print("Failed to capture frame")
                    sys.stdout.flush()
                    continue
                
                # Encode frame to JPEG
                _, buffer = cv2.imencode('.jpg', frame)
                image_data = buffer.tobytes()
                
                # Send size followed by image data
                size = len(image_data)
                try:
                    # Send 8-byte size header
                    size_header = str(size).zfill(8).encode()
                    client_socket.sendall(size_header)
                    
                    # Send image data
                    client_socket.sendall(image_data)
                    
                    image_count += 1
                    print(f"Sent image {image_count} (size: {size} bytes)")
                    sys.stdout.flush()
                    
                except socket.error as e:
                    print(f"Socket error while sending: {str(e)}")
                    sys.stdout.flush()
                    break
                
                # Wait 10 seconds before next capture
                time.sleep(10)
            
            print(f"Capture session completed. Sent {image_count} images.")
            sys.stdout.flush()
            
        except Exception as e:
            print(f"Error in capture_and_send: {str(e)}")
            sys.stdout.flush()
        finally:
            if self.camera:
                self.camera.release()
            self.camera = None
            self.stop_capture = False

    def handle_client(self, client_socket, addr):
        """Handle client connection and commands"""
        try:
            print(f"Handling connection from {addr}")
            sys.stdout.flush()
            
            # Receive command data
            data = client_socket.recv(1024).decode()
            if not data:
                return
            
            try:
                command = json.loads(data)
                print(f"Received command: {command}")
                sys.stdout.flush()
                
                if command.get('command') == 'start_capture':
                    request_id = command.get('request_id')
                    requester_email = command.get('requester_email')
                    
                    print(f"Starting capture for request {request_id} from {requester_email}")
                    sys.stdout.flush()
                    
                    # Start capture in current thread since we're already in a thread per client
                    self.capture_and_send(client_socket, request_id)
                    
            except json.JSONDecodeError as e:
                print(f"Invalid command format: {str(e)}")
                sys.stdout.flush()
                
        except Exception as e:
            print(f"Error handling client: {str(e)}")
            sys.stdout.flush()
        finally:
            try:
                client_socket.close()
            except:
                pass

    def run(self):
        """Run the camera service."""
        print("Starting camera service run method...")
        sys.stdout.flush()
        
        try:
            print("Checking v4l2-ctl installation...")
            sys.stdout.flush()
            subprocess.check_call(['which', 'v4l2-ctl'])
        except subprocess.CalledProcessError:
            print("v4l2-ctl not found, installing...")
            sys.stdout.flush()
            subprocess.check_call(['apt-get', 'update'])
            subprocess.check_call(['apt-get', 'install', '-y', 'v4l-utils'])
        
        print("Checking camera device...")
        sys.stdout.flush()
        try:
            if not os.path.exists('/dev/video0'):
                print("Error: Camera device /dev/video0 not found!")
                sys.stdout.flush()
                return
            
            device_stat = os.stat('/dev/video0')
            print(f"Camera device permissions: {oct(device_stat.st_mode)}")
            print(f"Camera device owner: {device_stat.st_uid}")
            print(f"Camera device group: {device_stat.st_gid}")
            sys.stdout.flush()
        except Exception as e:
            print(f"Error checking camera device: {str(e)}")
            sys.stdout.flush()
            return

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            print(f"Attempting to bind to {self.host}:{self.port}")
            sys.stdout.flush()
            server.bind((self.host, self.port))
            server.listen(1)
            
            print("Socket bound and listening")
            print(f"Camera service running on {self.host}:{self.port}")
            print(f"Ready to send images to Windows service at {self.windows_zerotier_ip}")
            print("Will capture 1 image every 10 seconds for 2 minutes when triggered")
            sys.stdout.flush()
            
            while True:
                client = None
                try:
                    print("Waiting for connection...")
                    sys.stdout.flush()
                    client, addr = server.accept()
                    
                    # Handle each client in a separate thread
                    thread = threading.Thread(
                        target=self.handle_client,
                        args=(client, addr)
                    )
                    thread.daemon = True
                    thread.start()
                    
                except Exception as e:
                    print(f"Error in connection loop: {str(e)}")
                    sys.stdout.flush()
                finally:
                    # Don't close client socket here as it's handled in the thread
                    pass
                        
        except Exception as e:
            print(f"Fatal error in server: {str(e)}")
            sys.stdout.flush()
            raise
        finally:
            print("Closing server socket")
            sys.stdout.flush()
            server.close()

if __name__ == "__main__":
    print("Main block starting...")
    sys.stdout.flush()
    
    try:
        service = CameraService()
        print("Service instance created, starting run method...")
        sys.stdout.flush()
        service.run()
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        sys.stdout.flush()
        raise