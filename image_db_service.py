from flask import Flask, request, jsonify
import os
from datetime import datetime
import sqlite3
import json

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

@app.route('/start_capture', methods=['POST'])
def start_capture():
    try:
        data = request.json
        requester_email = data.get('requester_email')
        timestamp = data.get('timestamp')
        
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
        
        return jsonify({
            'status': 'success',
            'request_id': request_id,
            'message': 'Capture request registered'
        }), 200
        
    except Exception as e:
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
    app.run(host='0.0.0.0', port=30081)