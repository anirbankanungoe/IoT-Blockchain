#!/usr/bin/env python3

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
        self.rpi_zerotier_ip = os.getenv('RPI_ZEROTIER_IP', '172.23.67.130')
        self.windows_zerotier_ip = os.getenv('WINDOWS_ZEROTIER_IP', '172.23.228.240')
        self.host = self.rpi_zerotier_ip  # Listen specifically on ZeroTier interface
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
            # Set GStreamer environment variable to suppress warnings
            os.environ['GST_DEBUG'] = '0'
            
            # Initialize camera with specific backend
            self.camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
            
            if not self.camera.isOpened():
                raise Exception("Could not open camera")
                
            # Set camera properties
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            
            print("Camera initialized successfully")
            sys.stdout.flush()
            return True
        except Exception as e:
            print(f"Error initializing camera: {str(e)}")
            sys.stdout.flush()
            return False

    def receive_ack(self, client_socket, expected_content=None):
        """Helper method to receive and validate acknowledgments"""
        try:
            ack_data = client_socket.recv(1024).decode()
            if not ack_data:
                print("No acknowledgment received")
                return False
                
            try:
                ack_json = json.loads(ack_data)
                if expected_content:
                    return expected_content in ack_json
                return True
            except json.JSONDecodeError:
                print("Invalid JSON in acknowledgment")
                return False
        except socket.timeout:
            print("Timeout waiting for acknowledgment")
            return False
        except Exception as e:
            print(f"Error receiving acknowledgment: {str(e)}")
            return False

    def capture_and_send(self, client_socket, request_id):
        """Capture images and send them to the client"""
        start_time = time.time()
        image_count = 0
        
        try:
            if not self.init_camera():
                print("Failed to initialize camera")
                return
            
            # Set socket timeout
            client_socket.settimeout(30)
            
            # Send start message and wait for acknowledgment
            start_message = json.dumps({
                'type': 'start',
                'request_id': request_id
            }).encode()
            
            # Send length of start message first
            msg_len = str(len(start_message)).zfill(8).encode()
            client_socket.sendall(msg_len)
            client_socket.sendall(start_message)
            
            # Wait for acknowledgment with retry
            retry_count = 3
            while retry_count > 0:
                if self.receive_ack(client_socket, 'ack'):
                    print("Received start acknowledgment")
                    break
                retry_count -= 1
                if retry_count > 0:
                    print(f"Retrying acknowledgment, {retry_count} attempts remaining")
                    time.sleep(1)
            
            if retry_count == 0:
                print("Failed to receive valid acknowledgment after retries")
                return
            
            while time.time() - start_time < 120 and not self.stop_capture:  # 2 minutes
                try:
                    # Capture frame
                    ret, frame = self.camera.read()
                    if not ret:
                        print("Failed to capture frame, retrying...")
                        time.sleep(1)
                        continue
                    
                    # Add timestamp to the image
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    cv2.putText(frame, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    
                    # Encode frame to JPEG with lower quality
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
                    _, buffer = cv2.imencode('.jpg', frame, encode_param)
                    image_data = buffer.tobytes()
                    
                    # Prepare image metadata
                    metadata = json.dumps({
                        'type': 'image',
                        'request_id': request_id,
                        'image_number': image_count + 1,
                        'timestamp': timestamp,
                        'size': len(image_data)
                    }).encode()
                    
                    # Send metadata length, metadata, then image data
                    metadata_len = str(len(metadata)).zfill(8).encode()
                    client_socket.sendall(metadata_len)
                    client_socket.sendall(metadata)
                    
                    # Send image data in chunks
                    remaining = len(image_data)
                    offset = 0
                    chunk_size = 8192
                    
                    while remaining > 0:
                        chunk = image_data[offset:offset + chunk_size]
                        sent = client_socket.send(chunk)
                        if sent == 0:
                            raise socket.error("Connection broken")
                        offset += sent
                        remaining -= sent
                    
                    # Wait for image acknowledgment with retry
                    if not self.receive_ack(client_socket, 'image_received'):
                        raise socket.error("Failed to receive valid image acknowledgment")
                    
                    image_count += 1
                    print(f"Successfully sent image {image_count}")
                    
                    # Wait before next capture
                    time.sleep(10)
                    
                except socket.error as e:
                    print(f"Socket error while sending: {str(e)}")
                    break
                except Exception as e:
                    print(f"Error during capture/send: {str(e)}")
                    break
                    
            print(f"Capture session completed. Sent {image_count} images.")
            
        except Exception as e:
            print(f"Error in capture_and_send: {str(e)}")
        finally:
            if self.camera:
                self.camera.release()
            self.camera = None
            self.stop_capture = False
            try:
                # Send end message
                end_message = json.dumps({
                    'type': 'end',
                    'request_id': request_id,
                    'total_images': image_count
                }).encode()
                msg_len = str(len(end_message)).zfill(8).encode()
                client_socket.sendall(msg_len)
                client_socket.sendall(end_message)
            except Exception as e:
                print(f"Error sending end message: {str(e)}")

    def handle_client(self, client_socket, addr):
        """Handle client connection and commands"""
        try:
            print(f"Handling connection from {addr}")
            sys.stdout.flush()
            
            # Set initial socket timeout
            client_socket.settimeout(30)
            
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
            try:
                subprocess.check_call(['apt-get', 'update'])
                subprocess.check_call(['apt-get', 'install', '-y', 'v4l-utils'])
            except subprocess.CalledProcessError as e:
                print(f"Error installing v4l-utils: {str(e)}")
                sys.stdout.flush()
                return
        
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
                    
        except Exception as e:
            print(f"Fatal error in server: {str(e)}")
            sys.stdout.flush()
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
        sys.exit(1)
