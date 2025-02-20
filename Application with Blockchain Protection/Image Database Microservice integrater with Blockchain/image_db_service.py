from flask import Flask, request, jsonify
import sqlite3
import os
from datetime import datetime
import json
import threading
from blockchain_client import BlockchainClient
from metrics_manager import BlockchainMetricsManager
from secure_socket import SecureSocket
import time

app = Flask(__name__)

class ImageDBService:
    def __init__(self):
        # Initialize paths
        self.db_path = '/app/data/images.db'
        self.images_dir = '/app/images'
        
        # Initialize directories
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
        
        # Initialize database
        self.init_db()
        
        # Blockchain configuration
        self.blockchain_enabled = os.getenv('BLOCKCHAIN_ENABLED', 'false').lower() == 'true'
        if self.blockchain_enabled:
            self.blockchain_client = BlockchainClient(
                service_id='image-db',
                private_key=os.getenv('BLOCKCHAIN_PRIVATE_KEY'),
                blockchain_url=os.getenv('BLOCKCHAIN_SERVICE_URL', 'http://blockchain-service:30083')
            )
            if not self.blockchain_client.register():
                raise Exception("Failed to register with blockchain service")
        
        # Initialize metrics manager
        self.metrics_manager = BlockchainMetricsManager()
        
        # Camera service configuration
        self.camera_host = os.getenv('CAMERA_SERVICE_HOST', '172.23.67.130')
        self.camera_port = int(os.getenv('CAMERA_SERVICE_PORT', '5555'))
        
        print(f"Image DB Service initialized with:")
        print(f"DB Path: {self.db_path}")
        print(f"Images Directory: {self.images_dir}")
        print(f"Blockchain Enabled: {self.blockchain_enabled}")
        print(f"Camera Service: {self.camera_host}:{self.camera_port}")

    def init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Create tables
        c.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                requester_email TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER,
                image_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                blockchain_verified BOOLEAN,
                FOREIGN KEY (request_id) REFERENCES requests (id)
            )
        ''')
        
        conn.commit()
        conn.close()

    def connect_to_camera_service(self, request_id, requester_email):
        """Connect to camera service with blockchain security if enabled"""
        start_time = time.time()
        
        try:
            # Create appropriate socket
            if self.blockchain_enabled:
                socket = SecureSocket(self.blockchain_client)
            else:
                socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Connect to camera service
            socket.connect((self.camera_host, self.camera_port))
            
            # Record connection metrics
            self.metrics_manager.record_delay(
                source_service='image-db',
                destination_service='camera',
                packet_id=f"conn-{request_id}",
                packet_size=0,
                delay_ms=(time.time() - start_time) * 1000,
                blockchain_enabled=self.blockchain_enabled
            )
            
            # Send capture command
            command = {
                'command': 'start_capture',
                'request_id': request_id,
                'requester_email': requester_email,
                'timestamp': int(time.time())
            }
            
            command_start = time.time()
            if self.blockchain_enabled:
                socket.send_secure(json.dumps(command))
            else:
                socket.sendall(json.dumps(command).encode())
            
            # Record command metrics
            self.metrics_manager.record_delay(
                source_service='image-db',
                destination_service='camera',
                packet_id=f"cmd-{request_id}",
                packet_size=len(json.dumps(command)),
                delay_ms=(time.time() - command_start) * 1000,
                blockchain_enabled=self.blockchain_enabled
            )
            
            # Handle incoming images
            self._handle_image_stream(socket, request_id, requester_email)
            
            return True
            
        except Exception as e:
            print(f"Error in camera service communication: {str(e)}")
            return False
        finally:
            socket.close()

    def _handle_image_stream(self, socket, request_id, requester_email):
        """Handle incoming image stream from camera"""
        try:
            while True:
                # Receive metadata
                if self.blockchain_enabled:
                    metadata = socket.receive_secure()
                else:
                    metadata_len = int(socket.recv(8).decode())
                    metadata = json.loads(socket.recv(metadata_len).decode())
                
                if metadata['type'] == 'end':
                    break
                
                if metadata['type'] == 'image':
                    # Record metrics before receiving image
                    start_time = time.time()
                    
                    # Receive image data
                    image_data = self._receive_image_data(socket, metadata['size'])
                    
                    # Save image and update database
                    if image_data:
                        self._save_image(image_data, request_id, metadata)
                        
                        # Record metrics
                        self.metrics_manager.record_delay(
                            source_service='camera',
                            destination_service='image-db',
                            packet_id=f"img-{request_id}-{metadata['image_number']}",
                            packet_size=len(image_data),
                            delay_ms=(time.time() - start_time) * 1000,
                            blockchain_enabled=self.blockchain_enabled
                        )
                        
                        # Forward image to email service
                        self._forward_to_email_service(
                            image_data,
                            request_id,
                            requester_email,
                            metadata
                        )
        
        except Exception as e:
            print(f"Error handling image stream: {str(e)}")

    def _receive_image_data(self, socket, size):
        """Receive image data with or without blockchain security"""
        try:
            image_data = bytearray()
            remaining = size
            
            while remaining > 0:
                chunk_size = min(remaining, 8192)
                if self.blockchain_enabled:
                    chunk = socket.receive_secure(chunk_size)
                else:
                    chunk = socket.recv(chunk_size)
                
                if not chunk:
                    raise Exception("Connection broken while receiving image")
                
                image_data.extend(chunk)
                remaining -= len(chunk)
            
            return bytes(image_data)
            
        except Exception as e:
            print(f"Error receiving image data: {str(e)}")
            return None

    def _save_image(self, image_data, request_id, metadata):
        """Save image to disk and update database"""
        try:
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"image_{request_id}_{timestamp}.jpg"
            filepath = os.path.join(self.images_dir, filename)
            
            