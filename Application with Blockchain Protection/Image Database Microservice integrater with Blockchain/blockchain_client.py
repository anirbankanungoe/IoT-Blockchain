import requests
import json
import time
from eth_account import Account
from web3 import Web3
import socket
import struct
import threading
from queue import Queue

class BlockchainClient:
    def __init__(self, service_id, private_key, blockchain_url):
        """Initialize blockchain client"""
        self.service_id = service_id
        self.account = Account.from_key(private_key)
        self.blockchain_url = blockchain_url
        self.web3 = Web3()
        self.enabled = True

    def register(self):
        """Register service with blockchain service"""
        if not self.enabled:
            return True

        try:
            response = requests.post(
                f"{self.blockchain_url}/register",
                json={
                    'service_id': self.service_id,
                    'public_key': self.account.address
                }
            )
            return response.status_code == 200
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

    def secure_request(self, url, method, data=None, files=None):
        """Make a secure HTTP request"""
        if not self.enabled:
            # Make regular request without blockchain security
            return requests.request(method, url, json=data, files=files)

        try:
            # Add timestamp and sign
            message_data = {
                'timestamp': int(time.time()),
                'data': data,
                'sender_id': self.service_id
            }

            signature = self.sign_message(message_data)

            # Add blockchain headers
            headers = {
                'X-Blockchain-Signature': signature,
                'X-Service-ID': self.service_id
            }

            return requests.request(
                method,
                url,
                json=message_data,
                headers=headers,
                files=files
            )

        except Exception as e:
            print(f"Error making secure request: {str(e)}")
            return None

class SecureSocket:
    """Socket wrapper with blockchain security"""
    
    def __init__(self, blockchain_client, existing_socket=None):
        self.blockchain_client = blockchain_client
        self.socket = existing_socket or socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.receive_queue = Queue()

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
            if isinstance(data, str):
                data = data.encode()
            return self