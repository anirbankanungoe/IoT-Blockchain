#!/usr/bin/env python3

import cv2
import time
import json
import os
import sys
import threading
from datetime import datetime
from blockchain_client import BlockchainClient
from metrics_manager import BlockchainMetricsManager
from secure_socket import SecureSocket, StandardSocket

class CameraService:
    def __init__(self):
        print("Initializing Camera Service...")
        sys.stdout.flush()
        
        # Network configuration
        self.rpi_zerotier_ip = os.getenv('RPI_ZEROTIER_IP', '172.23.67.130')
        self.windows_zerotier_ip = os.getenv('WINDOWS_ZEROTIER_IP', '172.23.228.240')
        self.host = self.rpi_zerotier_ip
        self.port = int(os.getenv('SERVICE_PORT', '5555'))
        
        # Blockchain configuration
        self.blockchain_enabled = os.getenv('BLOCKCHAIN_ENABLED', 'false').lower() == 'true'
        if self.blockchain_enabled:
            self.blockchain_client = BlockchainClient(
                service_id='camera-service',
                private_key=os.getenv('BLOCKCHAIN_PRIVATE_KEY'),
                blockchain_url=os.getenv('BLOCKCHAIN_SERVICE_URL', 'http://blockchain-service:30083')
            )
            if not self.blockchain_client.register():
                raise Exception("Failed to register with blockchain service")
        
        # Initialize metrics manager
        self.metrics_manager = BlockchainMetricsManager()
        
        # Camera state
        self.camera = None
        self.stop_capture = False
        
        print(f"Configuration loaded:")
        print(f"RPI ZeroTier IP: {self.rpi_zerotier_ip}")
        print(f"Windows ZeroTier IP: {self.windows_zerotier_ip}")
        print(f"Listening on: {self.host}:{self.port}")
        print(f"Blockchain Enabled: {self.blockchain_enabled}")
        sys.stdout.flush()

    def init_camera(self):
        """Initialize the camera device with performance metrics"""
        try:
            start_time = time.time()
            
            # Set GStreamer environment variable
            os.environ['GST_DEBUG'] = '0'
            
            # Initialize camera
            self.camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
            
            if not self.camera.isOpened():
                raise Exception("Could not open camera")
            
            # Set camera properties
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            
            # Record initialization metrics
            self.metrics_manager.record_delay(
                source_service='camera',
                destination_service='camera',
                packet_id='camera-init',
                packet_size=0,
                delay_ms=(time.time() - start_time) * 1000,
                blockchain_enabled=self.blockchain_enabled
            )
            
            print("Camera initialized successfully")
            return True
            
        except Exception as e:
            print(f"Error initializing camera: {str(e)}")
            return False

    def capture_and_send(self, client_socket, request_id):
        """Capture and send images with blockchain security and metrics"""
        start_time = time.time()
        image_count = 0
        
        try:
            if not self.init_camera():
                return
            
            # Create secure or standard socket wrapper
            socket = (
                SecureSocket(self.blockchain_client, existing_socket=client_socket)
                if self.blockchain_enabled
                else StandardSocket(client_socket)
            )
            
            # Send start message with metrics
            start_message = {
                'type': 'start',
                'request_id': request_id,
                'timestamp': int(time.time())
            }
            
            msg_start = time.time()
            socket.send(json.dumps(start_message))
            
            # Record start message metrics
            self.metrics_manager.record_delay(
                source_service='camera',
                destination_service='image-db',
                packet_id=f"start-{request_id}",
                packet_size=len(json.dumps(start_message)),
                delay_ms=(time.time() - msg_start) * 1000,
                blockchain_enabled=self.blockchain_enabled
            )
            
            # Main capture loop
            while time.time() - start_time < 120 and not self.stop_capture:
                try:
                    # Capture frame with metrics
                    capture_start = time.time()
                    ret, frame = self.camera.read()
                    
                    if not ret:
                        print("Failed to capture frame, retrying...")
                        time.sleep(1)
                        continue
                    
                    # Record capture metrics
                    self.metrics_manager.record_delay(
                        source_service='camera',
                        destination_service='camera',
                        packet_id=f"capture-{request_id}-{image_count}",
                        packet_size=frame.nbytes,
                        delay_ms=(time.time() - capture_start) * 1000,
                        blockchain_enabled=self.blockchain_enabled
                    )
                    
                    # Process image
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    cv2.putText(frame, timestamp, (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    
                    # Encode image
                    encode_start = time.time()
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
                    _, buffer = cv2.imencode('.jpg', frame, encode_param)
                    image_data = buffer.tobytes()
                    
                    # Record encoding metrics
                    self.metrics_manager.record_delay(
                        source_service='camera',
                        destination_service='camera',
                        packet_id=f"encode-{request_id}-{image_count}",
                        packet_size=len(image_data),
                        delay_ms=(time.time() - encode_start) * 1000,
                        blockchain_enabled=self.blockchain_enabled
                    )
                    
                    # Send image with metrics
                    send_start = time.time()
                    metadata = {
                        'type': 'image',
                        'request_id': request_id,
                        'image_number': image_count + 1,
                        'timestamp': timestamp,
                        'size': len(image_data)
                    }
                    
                    socket.send(json.dumps(metadata))
                    socket.send_raw(image_data)
                    
                    # Record sending metrics
                    self.metrics_manager.record_delay(
                        source_service='camera',
                        destination_service='image-db',
                        packet_id=f"send-{request_id}-{image_count}",
                        packet_size=len(image_data),
                        delay_ms=(time.time() - send_start) * 1000,
                        blockchain_enabled=self.blockchain_enabled
                    )
                    
                    image_count += 1
                    print(f"Successfully sent image {image_count}")
                    
                    # Record memory and CPU metrics
                    self.metrics_manager.record_memory_usage(
                        service_name='camera',
                        blockchain_enabled=self.blockchain_enabled
                    )
                    self.metrics_manager.record_cpu_usage(
                        service_name='camera',
                        blockchain_enabled=self.blockchain_enabled
                    )
                    
                    time.sleep(10)
                    
                except Exception as e:
                    print(f"Error in capture loop: {str(e)}")
                    break
            
        except Exception as e:
            print(f"Error in capture_and_send: {str(e)}")
        finally:
            if self.camera:
                self.camera.release()
            self.camera = None
            self.stop_capture = False
            
            # Send end message with metrics
            try:
                end_message = {
                    'type': 'end',
                    'request_id': request_id,
                    'total_images': image_count,
                    'timestamp': int(time.time())
                }
                
                end_start = time.time()
                socket.send(json.dumps(end_message))
                
                # Record end message metrics
                self.metrics_manager.record_delay(
                    source_service='camera',
                    destination_service='image-db',
                    packet_id=f"end-{request_id}",
                    packet_size=len(json.dumps(end_message)),
                    delay_ms=(time.time() - end_start) * 1000,
                    blockchain_enabled=self.blockchain_enabled
                )
                
            except Exception as e:
                print(f"Error sending end message: {str(e)}")

    def handle_client(self, client_socket, addr):
        """Handle client connection with blockchain security"""
        try:
            print(f"Handling connection from {addr}")
            
            # Create secure or standard socket wrapper
            socket = (
                SecureSocket(self.blockchain_client, existing_socket=client_socket)
                if self.blockchain_enabled
                else StandardSocket(client_socket)
            )
            
            # Receive command
            command_data = socket.receive()
            if not command_data:
                return
            
            command = json.loads(command_data)
            print(f"Received command: