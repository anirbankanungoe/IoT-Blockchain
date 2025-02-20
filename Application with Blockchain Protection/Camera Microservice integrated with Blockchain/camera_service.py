#!/usr/bin/env python3

import cv2
import time
import json
import os
import sys
import socket
import struct
import threading
from queue import Queue
from datetime import datetime
from web3 import Web3
from eth_account import Account

# Implementation of Socket classes
class StandardSocket:
    """Standard socket without blockchain security"""
    
    def __init__(self, socket):
        self.socket = socket
    
    def send(self, data):
        """Send string data"""
        if isinstance(data, str):
            data = data.encode()
        
        # Send with size prefix for framing
        size = len(data)
        self.socket.sendall(struct.pack('!I', size))
        self.socket.sendall(data)
    
    def send_raw(self, data):
        """Send raw binary data without size prefix"""
        self.socket.sendall(data)
    
    def receive(self, max_size=None):
        """Receive string data with size prefix"""
        # First read the 4-byte size
        size_data = self.socket.recv(4)
        if not size_data or len(size_data) < 4:
            return None
            
        size = struct.unpack('!I', size_data)[0]
        
        # Then read the payload
        data = bytearray()
        remaining = size
        
        while remaining > 0:
            chunk = self.socket.recv(min(remaining, 4096))
            if not chunk:
                break
            data.extend(chunk)
            remaining -= len(chunk)
            
        return data.decode()
    
    def receive_raw(self, size):
        """Receive exact amount of binary data"""
        data = bytearray()
        remaining = size
        
        while remaining > 0:
            chunk = self.socket.recv(min(remaining, 4096))
            if not chunk:
                break
            data.extend(chunk)
            remaining -= len(chunk)
            
        return bytes(data)

class SecureSocket:
    """Socket wrapper with blockchain security"""
    
    def __init__(self, blockchain_client, existing_socket=None):
        self.blockchain_client = blockchain_client
        self.socket = existing_socket or socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    def connect(self, address):
        """Connect to remote address"""
        self.socket.connect(address)
        if self.blockchain_client.enabled:
            self._perform_handshake()
    
    def _perform_handshake(self):
        """Perform blockchain security handshake"""
        handshake_data = {
            'service_id': self.blockchain_client.service_id,
            'timestamp': int(time.time())
        }

        signature = self.blockchain_client.sign_message(handshake_data)
        message = {
            'type': 'handshake',
            'data': handshake_data,
            'signature': signature
        }

        self._send_json(message)
        response = self._receive_json()

        if not response or response.get('type') != 'handshake_ack':
            raise Exception("Blockchain handshake failed")
    
    def send(self, data):
        """Send data with blockchain security"""
        if not self.blockchain_client.enabled:
            # Use StandardSocket behavior if blockchain disabled
            if isinstance(data, str):
                data = data.encode()
            size = len(data)
            self.socket.sendall(struct.pack('!I', size))
            self.socket.sendall(data)
            return
            
        # For text data, use secure JSON
        if isinstance(data, str):
            try:
                # Try to parse as JSON first
                json_data = json.loads(data)
                message_data = {
                    'timestamp': int(time.time()),
                    'data': json_data,
                    'sender_id': self.blockchain_client.service_id
                }
            except:
                # Not JSON, treat as plain text
                message_data = {
                    'timestamp': int(time.time()),
                    'data': data,
                    'sender_id': self.blockchain_client.service_id
                }
                
            signature = self.blockchain_client.sign_message(message_data)
            wrapped_message = {
                'message': message_data,
                'signature': signature
            }
            
            self._send_json(wrapped_message)
    
    def send_raw(self, data):
        """Send binary data with minimal blockchain overhead"""
        if not self.blockchain_client.enabled:
            self.socket.sendall(data)
            return
            
        # For binary data, we only sign the size and timestamp
        # to avoid overhead of encoding binary data as JSON
        header = {
            'timestamp': int(time.time()),
            'size': len(data),
            'sender_id': self.blockchain_client.service_id
        }
        
        signature = self.blockchain_client.sign_message(header)
        
        # Send header with signature
        header_with_sig = {
            'header': header,
            'signature': signature
        }
        
        header_json = json.dumps(header_with_sig).encode()
        header_size = len(header_json)
        
        # Send header size, header, then raw data
        self.socket.sendall(struct.pack('!I', header_size))
        self.socket.sendall(header_json)
        self.socket.sendall(data)
    
    def receive(self):
        """Receive text data with blockchain verification"""
        if not self.blockchain_client.enabled:
            # First read the 4-byte size
            size_data = self.socket.recv(4)
            if not size_data or len(size_data) < 4:
                return None
                
            size = struct.unpack('!I', size_data)[0]
            
            # Then read the payload
            data = bytearray()
            remaining = size
            
            while remaining > 0:
                chunk = self.socket.recv(min(remaining, 4096))
                if not chunk:
                    break
                data.extend(chunk)
                remaining -= len(chunk)
                
            return data.decode()
            
        wrapped_message = self._receive_json()
        
        if not wrapped_message:
            return None
            
        # Verify signature
        if not self.blockchain_client.verify_signature(
            wrapped_message['message'],
            wrapped_message['signature']
        ):
            raise Exception("Invalid blockchain signature")
            
        return json.dumps(wrapped_message['message']['data'])
    
    def _send_json(self, data):
        """Send JSON data with size prefix"""
        serialized = json.dumps(data).encode()
        size = len(serialized)
        self.socket.sendall(struct.pack('!I', size))
        self.socket.sendall(serialized)
    
    def _receive_json(self):
        """Receive JSON data with size prefix"""
        try:
            size_data = self.socket.recv(4)
            if not size_data or len(size_data) < 4:
                return None
                
            size = struct.unpack('!I', size_data)[0]
            
            data = bytearray()
            remaining = size
            
            while remaining > 0:
                chunk = self.socket.recv(min(remaining, 4096))
                if not chunk:
                    return None
                data.extend(chunk)
                remaining -= len(chunk)
                
            return json.loads(data.decode())
            
        except Exception as e:
            print(f"Error receiving JSON: {str(e)}")
            return None

# Blockchain client implementation
class BlockchainClient:
    def __init__(self, service_id, private_key, blockchain_url):
        """Initialize blockchain client"""
        self.service_id = service_id
        self.account = Account.from_key(private_key)
        self.blockchain_url = blockchain_url
        self.web3 = Web3()
        self.enabled = True
        print(f"Initialized blockchain client for {service_id} with public key {self.account.address}")

    def register(self):
        """Register service with blockchain service"""
        if not self.enabled:
            return True

        try:
            import requests
            print(f"Registering with blockchain service at {self.blockchain_url}...")
            response = requests.post(
                f"{self.blockchain_url}/register",
                json={
                    'service_id': self.service_id,
                    'public_key': self.account.address
                }
            )
            success = response.status_code == 200
            if success:
                print("Successfully registered with blockchain service")
            else:
                print(f"Failed to register: {response.text}")
            return success
        except Exception as e:
            print(f"Error registering with blockchain: {str(e)}")
            return False

    def sign_message(self, message_data):
        """Sign a message with service's private key"""
        message_hash = self.web3.keccak(text=json.dumps(message_data, sort_keys=True))
        signed_message = self.account.sign_message(message_hash)
        return signed_message.signature.hex()

    def verify_signature(self, message_data, signature):
        """Verify a message signature"""
        try:
            import requests
            response = requests.post(
                f"{self.blockchain_url}/verify",
                json={
                    'message': message_data,
                    'signature': signature,
                    'sender_id': message_data.get('sender_id')
                }
            )
            return response.status_code == 200 and response.json().get('is_valid')
        except Exception as e:
            print(f"Error verifying signature: {str(e)}")
            return False

# Metrics manager for the camera service
class BlockchainMetricsManager:
    def __init__(self, base_path="/app/metrics"):
        """Initialize the metrics manager"""
        self.base_path = os.path.join(base_path)
        os.makedirs(self.base_path, exist_ok=True)
        os.makedirs(os.path.join(self.base_path, 'delay', 'summaries'), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, 'memory', 'summaries'), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, 'cpu', 'summaries'), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, 'comparisons'), exist_ok=True)
        
        # Create locks for file access
        self.file_locks = {
            'delay': threading.Lock(),
            'memory': threading.Lock(),
            'cpu': threading.Lock()
        }
        
        # Initialize files if they don't exist
        self._initialize_dataframes()
        
        print("Initialized BlockchainMetricsManager")

    def _initialize_dataframes(self):
        """Initialize metrics files with headers if they don't exist"""
        try:
            import pandas as pd
            
            files_and_headers = {
                'delay/raw_data.csv': [
                    'timestamp', 'source_service', 'destination_service',
                    'packet_id', 'packet_size', 'delay_ms', 'blockchain_enabled'
                ],
                'memory/raw_data.csv': [
                    'timestamp', 'service_name', 'memory_usage_mb',
                    'blockchain_enabled', 'total_memory_mb', 'memory_percent'
                ],
                'cpu/raw_data.csv': [
                    'timestamp', 'service_name', 'cpu_percent',
                    'blockchain_enabled', 'core_count', 'cpu_freq_mhz'
                ]
            }
            
            for file_path, headers in files_and_headers.items():
                full_path = os.path.join(self.base_path, file_path)
                if not os.path.exists(full_path):
                    df = pd.DataFrame(columns=headers)
                    df.to_csv(full_path, index=False)
                    print(f"Created metrics file: {full_path}")
                    
        except Exception as e:
            print(f"Error initializing metrics files: {str(e)}")

    def record_delay(self, source_service, destination_service, packet_id, 
                    packet_size, delay_ms, blockchain_enabled):
        """Record packet delay metrics"""
        with self.file_locks['delay']:
            try:
                import pandas as pd
                file_path = os.path.join(self.base_path, 'delay', 'raw_data.csv')
                
                # Read existing data or create new DataFrame
                try:
                    df = pd.read_csv(file_path)
                except:
                    df = pd.DataFrame(columns=[
                        'timestamp', 'source_service', 'destination_service',
                        'packet_id', 'packet_size', 'delay_ms', 'blockchain_enabled'
                    ])
                
                # Add new row
                new_row = {
                    'timestamp': datetime.now().isoformat(),
                    'source_service': source_service,
                    'destination_service': destination_service,
                    'packet_id': packet_id,
                    'packet_size': packet_size,
                    'delay_ms': delay_ms,
                    'blockchain_enabled': blockchain_enabled
                }
                
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(file_path, index=False)
                
            except Exception as e:
                print(f"Error recording delay metrics: {str(e)}")

    def record_memory_usage(self, service_name, blockchain_enabled):
        """Record memory usage metrics"""
        with self.file_locks['memory']:
            try:
                import pandas as pd
                import psutil
                
                file_path = os.path.join(self.base_path, 'memory', 'raw_data.csv')
                
                # Read existing data or create new DataFrame
                try:
                    df = pd.read_csv(file_path)
                except:
                    df = pd.DataFrame(columns=[
                        'timestamp', 'service_name', 'memory_usage_mb',
                        'blockchain_enabled', 'total_memory_mb', 'memory_percent'
                    ])
                
                process = psutil.Process()
                memory_info = process.memory_info()
                
                new_row = {
                    'timestamp': datetime.now().isoformat(),
                    'service_name': service_name,
                    'memory_usage_mb': memory_info.rss / 1024 / 1024,
                    'blockchain_enabled': blockchain_enabled,
                    'total_memory_mb': psutil.virtual_memory().total / 1024 / 1024,
                    'memory_percent': process.memory_percent()
                }
                
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(file_path, index=False)
                
            except Exception as e:
                print(f"Error recording memory metrics: {str(e)}")

    def record_cpu_usage(self, service_name, blockchain_enabled):
        """Record CPU usage metrics"""
        with self.file_locks['cpu']:
            try:
                import pandas as pd
                import psutil
                
                file_path = os.path.join(self.base_path, 'cpu', 'raw_data.csv')
                
                # Read existing data or create new DataFrame
                try:
                    df = pd.read_csv(file_path)
                except:
                    df = pd.DataFrame(columns=[
                        'timestamp', 'service_name', 'cpu_percent',
                        'blockchain_enabled', 'core_count', 'cpu_freq_mhz'
                    ])
                
                process = psutil.Process()
                
                new_row = {
                    'timestamp': datetime.now().isoformat(),
                    'service_name': service_name,
                    'cpu_percent': process.cpu_percent(interval=0.1),
                    'blockchain_enabled': blockchain_enabled,
                    'core_count': psutil.cpu_count(),
                    'cpu_freq_mhz': psutil.cpu_freq().current if psutil.cpu_freq() else 0
                }
                
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(file_path, index=False)
                
            except Exception as e:
                print(f"Error recording CPU metrics: {str(e)}")

# Main Camera Service class
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
            private_key = os.getenv('BLOCKCHAIN_PRIVATE_KEY')
            if not private_key:
                print("ERROR: BLOCKCHAIN_PRIVATE_KEY environment variable not set")
                sys.exit(1)
                
            blockchain_url = os.getenv('BLOCKCHAIN_SERVICE_URL', 'http://blockchain-service:30083')
            self.blockchain_client = BlockchainClient(
                service_id='camera-service',
                private_key=private_key,
                blockchain_url=blockchain_url
            )
            if not self.blockchain_client.register():
                print("WARNING: Failed to register with blockchain service, will retry periodically")
        else:
            print("Blockchain security is DISABLED")
        
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
        
        # Check camera availability
        if not self._check_camera_device():
            print("WARNING: Camera device not found or not accessible")
        else:
            print("Camera device is available")

    def _check_camera_device(self):
        """Check if camera device is available"""
        try:
            # Try to open camera briefly
            cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
            if cap.isOpened():
                ret, _ = cap.read()
                cap.release()
                return ret
            return False
        except Exception as e:
            print(f"Error checking camera: {str(e)}")
            return False

    def init_camera(self):
        """Initialize the camera device with performance metrics"""
        try:
            start_time = time.time()
            
            # Set GStreamer environment variable
            os.environ['GST_DEBUG'] = '0'
            
            # Initialize camera
            self.camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
            
            if not self.camera.isOpened():
                print("Failed to open camera device")
                return False
            
            # Set camera properties
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            
            # Test capture
            ret, _ = self.camera.read()
            if not ret:
                print("Failed to capture test frame")
                self.camera.release()
                self.camera = None
                return False
            
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
            if self.camera:
                self.camera.release()
                self.camera = None
            return False

    def capture_and_send(self, client_socket, request_id, requester_email):
        """Capture and send images with blockchain security and metrics"""
        start_time = time.time()
        image_count = 0
        
        try:
            if not self.init_camera():
                print("Failed to initialize camera")
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
                'requester_email': requester_email,
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
            
            print(f"Starting image capture for request {request_id} (email: {requester_email})")
            
            # Main capture loop - 2 minutes of capture time
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
                    
                    # Process image - add timestamp overlay
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
                    
                    # Send image metadata
                    send_start = time.time()
                    metadata = {
                        'type': 'image',
                        'request_id': request_id,
                        'image_number': image_count + 1,
                        'timestamp': timestamp,
                        'size': len(image_data),
                        'requester_email': requester_email
                    }
                    
                    socket.send(json.dumps(metadata))
                    
                    # Send actual image data
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
                    
                    # Wait between captures to reduce load and bandwidth
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
                
                print(f"Capture completed: sent {image_count} images")
                
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
                print("Received empty command data")
                return
            
            command = json.loads(command_data)
            print(f"Received command: {command['command']} from {addr}")
            
            if command['command'] == 'start_capture':
                request_id = command.get('request_id', str(int(time.time())))
                requester_email = command.get('requester_email', 'unknown@example.com')
                
                # Start capture in a new thread
                capture_thread = threading.Thread(
                    target=self.capture_and_send,
                    args=(client_socket, request_id, requester_email)
                )
                capture_thread.daemon = True
                capture_thread.start()
                
                # Don't close the socket - the capture thread will handle it
                return True
            else:
                print(f"Unknown command: {command['command']}")
                return False
                
        except Exception as e:
            print(f"Error handling client: {str(e)}")
            client_socket.close()
            return False

    def start_server(self):
        """Start the camera service server"""
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, self.port))
            server_socket.listen(5)
            
            print(f"Camera service listening on {self.host}:{self.port}")
            
            while True:
                try:
                    client_socket, addr = server_socket.accept()
                    print(f"Accepted connection from {addr}")
                    
                    # Handle client in a new thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, addr)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except Exception as e:
                    print(f"Error accepting connection: {str(e)}")
                    time.sleep(1)
                    
        except Exception as e:
            print(f"Error starting server: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    # Initialize camera service
    camera_service = CameraService()
    
    # Start server
    print("Starting Camera Service...")
    sys.stdout.flush()
    camera_service.start_server()