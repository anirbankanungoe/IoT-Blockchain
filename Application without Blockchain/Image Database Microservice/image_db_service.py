import requests
from flask import Flask, request, jsonify
import os
from datetime import datetime
import sqlite3
import json
import socket  # Added for camera service communication

app = Flask(__name__)

DB_PATH = '/app/data/images.db'
IMAGES_DIR = '/app/images'

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS requests
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         timestamp TEXT NOT NULL,
         requester_email TEXT NOT NULL,
         status TEXT NOT NULL,
         created_at TEXT NOT NULL)
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS images
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         request_id INTEGER,
         image_path TEXT NOT NULL,
         created_at TEXT NOT NULL,
         FOREIGN KEY (request_id) REFERENCES requests (id))
    ''')
    
    conn.commit()
    conn.close()

def send_to_email_service(image_data, filename, requester_email, request_id):
    """Send image to email handler service"""
    try:
        # Create files dictionary with image data
        files = {
            'image': (filename, image_data, 'image/jpeg')
        }
        
        # Create form data
        form_data = {
            'requester_email': requester_email,
            'request_id': request_id
        }
        
        # Send to email handler service
        response = requests.post(
            'http://172.23.228.240:30082/send_image',  # Email handler service address
            files=files,
            data=form_data
        )
        
        if response.status_code == 200:
            print(f"Successfully sent image {filename} to email service")
            return True
        else:
            print(f"Failed to send image to email service: {response.text}")
            return False
            
    except Exception as e:
        print(f"Error sending image to email service: {str(e)}")
        return False

def connect_to_camera_service(request_id, requester_email):
    """Connect to camera service and request image capture"""
    camera_socket = None
    try:
        # Create socket connection to camera service
        camera_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        camera_socket.settimeout(30)  # Increased timeout to 30 seconds
        camera_socket.connect(('172.23.67.130', 5555))  # Connect to RPI ZeroTier IP
        
        # Prepare command
        command = {
            'command': 'start_capture',
            'request_id': request_id,
            'requester_email': requester_email
        }
        
        # Send command
        camera_socket.sendall(json.dumps(command).encode())
        print(f"Sent capture command to camera service for request {request_id}")
        
        # Receive start message length
        msg_len = int(camera_socket.recv(8).decode())
        # Receive start message
        start_message = camera_socket.recv(msg_len).decode()
        start_data = json.loads(start_message)
        
        if start_data.get('type') == 'start':
            # Send acknowledgment
            ack_message = json.dumps({"ack": True}).encode()
            camera_socket.sendall(ack_message)
            print("Sent start acknowledgment")
            
            # Start receiving images
            while True:
                try:
                    # Receive metadata length
                    metadata_len = int(camera_socket.recv(8).decode())
                    # Receive metadata
                    metadata = camera_socket.recv(metadata_len).decode()
                    metadata_json = json.loads(metadata)
                    
                    if metadata_json.get('type') == 'end':
                        print(f"Received end message. Total images: {metadata_json.get('total_images')}")
                        break
                        
                    if metadata_json.get('type') == 'image':
                        image_size = metadata_json.get('size')
                        
                        # Create a buffer for the image
                        image_data = bytearray()
                        remaining = image_size
                        
                        # Receive image data in chunks
                        while remaining > 0:
                            chunk_size = min(remaining, 8192)
                            chunk = camera_socket.recv(chunk_size)
                            if not chunk:
                                raise Exception("Connection broken while receiving image")
                            image_data.extend(chunk)
                            remaining -= len(chunk)
                        
                        # Save the image
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"image_{request_id}_{timestamp}.jpg"
                        filepath = os.path.join(IMAGES_DIR, filename)
                        
                        with open(filepath, 'wb') as f:
                            f.write(image_data)
                        
                        # Update database
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO images (request_id, image_path, created_at)
                            VALUES (?, ?, ?)
                        ''', (request_id, filepath, datetime.now().isoformat()))
                        conn.commit()
                        conn.close()
                        
                        # Send to email service
                        print(f"Sending image {filename} to email service...")
                        send_to_email_service(image_data, filename, requester_email, request_id)
                        
                        # Send image acknowledgment
                        image_ack = json.dumps({"image_received": True}).encode()
                        camera_socket.sendall(image_ack)
                        print(f"Image {metadata_json.get('image_number')} received and acknowledged")
                
                except socket.timeout:
                    print("Timeout while receiving image")
                    break
                except Exception as e:
                    print(f"Error receiving image: {str(e)}")
                    break
            
        return True
        
    except Exception as e:
        print(f"Error in camera service communication: {str(e)}")
        return False
    finally:
        try:
            if camera_socket:
                camera_socket.close()
        except:
            pass

@app.route('/start_capture', methods=['POST'])
def start_capture():
    try:
        data = request.json
        requester_email = data.get('requester_email')
        timestamp = data.get('timestamp')
        
        print(f"Received capture request for {requester_email}")
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Store the request
        c.execute('''
            INSERT INTO requests (timestamp, requester_email, status, created_at)
            VALUES (?, ?, ?, ?)
        ''', (
            timestamp,
            requester_email,
            'pending',
            datetime.now().isoformat()
        ))
        
        request_id = c.lastrowid
        conn.commit()
        conn.close()
        
        print(f"Created request with ID: {request_id}")
        
        # Connect to camera service and start capture
        success = connect_to_camera_service(request_id, requester_email)
        
        if success:
            print(f"Successfully connected to camera service for request {request_id}")
            return jsonify({
                'status': 'success',
                'request_id': request_id,
                'message': 'Capture request registered and camera service notified'
            }), 200
        else:
            print(f"Failed to connect to camera service for request {request_id}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to connect to camera service'
            }), 500
            
    except Exception as e:
        print(f"Error processing capture request: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/store_image', methods=['POST'])
def store_image():
    """Store received image from camera service"""
    try:
        if 'image' not in request.files:
            return jsonify({'status': 'error', 'message': 'No image file'}), 400
            
        image_file = request.files['image']
        request_id = request.form.get('request_id')
        
        if not request_id:
            return jsonify({'status': 'error', 'message': 'No request ID'}), 400
            
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"image_{request_id}_{timestamp}.jpg"
        filepath = os.path.join(IMAGES_DIR, filename)
        
        # Save image file
        image_file.save(filepath)
        
        # Update database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO images (request_id, image_path, created_at)
            VALUES (?, ?, ?)
        ''', (request_id, filepath, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': 'Image stored successfully',
            'filepath': filepath
        }), 200
        
    except Exception as e:
        print(f"Error storing image: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    # Initialize database at startup
    init_db()
    print(f"Starting Image Database Service on port 30081...")
    app.run(host='172.23.228.240', port=30081)