from flask import Flask, request, jsonify
import hashlib
import json
import time
from eth_account import Account
from web3 import Web3
import threading
from datetime import datetime
import os
from metrics_manager import BlockchainMetricsManager

app = Flask(__name__)

class BlockchainService:
    def __init__(self):
        # Initialize paths
        self.blockchain_dir = '/app/blockchain'
        os.makedirs(self.blockchain_dir, exist_ok=True)
        
        # Initialize blockchain state
        self.services = {}  # Registered services
        self.message_cache = {}  # Message cache for replay protection
        self.locks = {
            'services': threading.Lock(),
            'cache': threading.Lock()
        }
        
        # Initialize Web3
        self.web3 = Web3()
        
        # Initialize metrics manager
        self.metrics_enabled = os.getenv('METRICS_ENABLED', 'true').lower() == 'true'
        if self.metrics_enabled:
            self.metrics_manager = BlockchainMetricsManager()
        
        print("Blockchain Service initialized")

    def register_service(self, service_id, public_key):
        """Register a new service"""
        with self.locks['services']:
            start_time = time.time()
            
            # Register service
            self.services[service_id] = {
                'public_key': public_key,
                'registered_at': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat()
            }
            
            # Record metrics if enabled
            if self.metrics_enabled:
                self.metrics_manager.record_delay(
                    source_service=service_id,
                    destination_service='blockchain',
                    packet_id=f"reg-{service_id}",
                    packet_size=len(public_key),
                    delay_ms=(time.time() - start_time) * 1000,
                    blockchain_enabled=True
                )
            
            return True

    def verify_message(self, message_data, signature, sender_id):
        """Verify a message's authenticity"""
        start_time = time.time()
        
        try:
            if sender_id not in self.services:
                return False
            
            # Create message hash
            message_hash = hashlib.sha256(
                f"{sender_id}{message_data['timestamp']}".encode()
            ).hexdigest()
            
            with self.locks['cache']:
                # Prevent replay attacks
                if message_hash in self.message_cache:
                    return False
                
                # Verify timestamp (5 minute window)
                if abs(int(time.time()) - message_data['timestamp']) > 300:
                    return False
                
                # Cache message hash
                self.message_cache[message_hash] = time.time()
                self._clean_message_cache()
            
            # Verify signature
            try:
                signed_hash = self.web3.keccak(text=json.dumps(message_data, sort_keys=True))
                recovered_address = Account.recover_message(signed_hash, signature=signature)
                is_valid = recovered_address.lower() == self.services[sender_id]['public_key'].lower()
                
                # Record metrics if enabled
                if self.metrics_enabled:
                    self.metrics_manager.record_delay(
                        source_service=sender_id,
                        destination_service='blockchain',
                        packet_id=message_hash[:8],
                        packet_size=len(json.dumps(message_data)),
                        delay_ms=(time.time() - start_time) * 1000,
                        blockchain_enabled=True
                    )
                
                return is_valid
                
            except Exception as e:
                print(f"Error verifying signature: {str(e)}")
                return False
            
        except Exception as e:
            print(f"Error verifying message: {str(e)}")
            return False

    def _clean_message_cache(self):
        """Clean old messages from cache"""
        current_time = time.time()
        with self.locks['cache']:
            self.message_cache = {
                msg_id: timestamp 
                for msg_id, timestamp in self.message_cache.items() 
                if current_time - timestamp < 3600  # 1 hour window
            }

    def record_metrics(self):
        """Record service metrics"""
        if self.metrics_enabled:
            self.metrics_manager.record_memory_usage(
                service_name='blockchain',
                blockchain_enabled=True
            )
            self.metrics_manager.record_cpu_usage(
                service_name='blockchain',
                blockchain_enabled=True
            )

# Flask routes
@app.route('/register', methods=['POST'])
def register_service():
    """Register a new service"""
    try:
        data = request.json
        service_id = data.get('service_id')
        public_key = data.get('public_key')
        
        if not all([service_id, public_key]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields'
            }), 400
        
        success = app.blockchain_service.register_service(service_id, public_key)
        
        return jsonify({
            'status': 'success' if success else 'error',
            'message': 'Service registered successfully' if success else 'Registration failed'
        }), 200 if success else 400
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/verify', methods=['POST'])
def verify_message():
    """Verify a message's authenticity"""
    try:
        data = request.json
        message_data = data.get('message')
        signature = data.get('signature')
        sender_id = data.get('sender_id')
        
        if not all([message_data, signature, sender_id]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields'
            }), 400
        
        is_valid = app.blockchain_service.verify_message(
            message_data,
            signature,
            sender_id
        )
        
        return jsonify({
            'status': 'success',
            'is_valid': is_valid
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

def start_metrics_recording():
    """Start periodic metrics recording"""
    while True:
        try:
            app.blockchain_service.record_metrics()
            time.sleep(60)  # Record metrics every minute
        except Exception as e:
            print(f"Error recording metrics: {str(e)}")
            time.sleep(10)

if __name__ == "__main__":
    # Initialize blockchain service
    app.blockchain_service = BlockchainService()
    
    # Start metrics recording if enabled
    if app.blockchain_service.metrics_enabled:
        metrics_thread = threading.Thread(target=start_metrics_recording)
        metrics_thread.daemon = True
        metrics_thread.start()
    
    # Start Flask server
    print("Starting Blockchain Service...")
    app.run(host='0.0.0.0', port=30083, threaded=True)