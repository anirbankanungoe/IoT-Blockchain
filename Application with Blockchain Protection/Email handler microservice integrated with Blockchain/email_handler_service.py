from flask import Flask, request, jsonify
import imaplib
import email
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import time
import requests
import os
import json
from datetime import datetime
import threading
from blockchain_client import BlockchainClient
from metrics_manager import BlockchainMetricsManager

app = Flask(__name__)

class EmailHandlerService:
    def __init__(self):
        # Email configuration
        self.email_address = os.getenv('EMAIL_ADDRESS')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.imap_server = "imap.gmail.com"
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 465
        
        # Initialize metrics manager
        self.metrics_manager = BlockchainMetricsManager()
        
        # Blockchain configuration
        self.blockchain_enabled = os.getenv('BLOCKCHAIN_ENABLED', 'false').lower() == 'true'
        if self.blockchain_enabled:
            print("Initializing blockchain client...")
            self.blockchain_client = BlockchainClient(
                service_id='email-handler',
                private_key=os.getenv('BLOCKCHAIN_PRIVATE_KEY'),
                blockchain_url=os.getenv('BLOCKCHAIN_SERVICE_URL', 'http://blockchain-service:30083')
            )
            # Register with blockchain service
            if not self.blockchain_client.register():
                raise Exception("Failed to register with blockchain service")
            print("Successfully registered with blockchain service")
        
        # Service URLs
        self.db_service_url = os.getenv('DB_SERVICE_URL', 'http://image-db-service:30081')
        
        print(f"Email Handler Service initialized with:")
        print(f"Email: {self.email_address}")
        print(f"DB Service URL: {self.db_service_url}")
        print(f"Blockchain Enabled: {self.blockchain_enabled}")

    def start_monitoring(self):
        """Start email monitoring in a separate thread."""
        monitor_thread = threading.Thread(target=self.run)
        monitor_thread.daemon = True
        monitor_thread.start()

    def check_emails(self):
        """Check for new emails requesting pictures."""
        try:
            start_time = time.time()
            
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.email_password)
            mail.select('inbox')
            
            # Search for unread emails
            _, messages = mail.search(None, 'UNSEEN')
            
            for num in messages[0].split():
                _, msg = mail.fetch(num, '(RFC822)')
                email_body = msg[0][1]
                email_message = email.message_from_bytes(email_body)
                
                # Record email check metrics
                self.metrics_manager.record_delay(
                    source_service='email-handler',
                    destination_service='email-server',
                    packet_id=f"check-{num.decode()}",
                    packet_size=len(email_body),
                    delay_ms=(time.time() - start_time) * 1000,
                    blockchain_enabled=self.blockchain_enabled
                )
                
                sender = email.utils.parseaddr(email_message['from'])[1]
                subject = email_message['subject'] or ''
                
                body = ""
                if email_message.is_multipart():
                    for part in email_message.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = email_message.get_payload(decode=True).decode()
                
                print(f"Processing email from {sender}")
                print(f"Subject: {subject}")
                
                # Process commands
                if 'send pictures for 2 minutes' in body.lower():
                    self._handle_picture_request(sender)
                elif 'give latest status' in subject.lower():
                    self._handle_status_request(sender)
                
                # Mark as read
                mail.store(num, '+FLAGS', '\\Seen')
            
            mail.logout()
            
        except Exception as e:
            print(f"Error checking emails: {str(e)}")

    def _make_secure_request(self, url, method='POST', data=None, files=None):
        """Make a secure request with blockchain verification and metrics"""
        start_time = time.time()
        
        try:
            if self.blockchain_enabled:
                response = self.blockchain_client.secure_request(url, method, data)
            else:
                if method.lower() == 'post':
                    response = requests.post(url, json=data, files=files)
                else:
                    response = requests.get(url, params=data)
            
            # Record metrics
            self.metrics_manager.record_delay(
                source_service='email-handler',
                destination_service='image-db',
                packet_id=f"{int(start_time)}",
                packet_size=len(json.dumps(data)) if data else 0,
                delay_ms=(time.time() - start_time) * 1000,
                blockchain_enabled=self.blockchain_enabled
            )
            
            return response
            
        except Exception as e:
            print(f"Error making secure request: {str(e)}")
            return None

    def _handle_picture_request(self, requester_email):
        """Handle request for pictures with blockchain security"""
        try:
            start_time = time.time()
            
            response = self._make_secure_request(
                f"{self.db_service_url}/start_capture",
                'POST',
                {
                    'requester_email': requester_email,
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            if response and response.status_code == 200:
                print("Capture request successful")
                self._send_confirmation_email(
                    requester_email,
                    "Picture capture started",
                    "Your request for pictures has been received. Images will be sent shortly."
                )
            else:
                error_msg = response.text if response else "No response"
                print(f"Capture request failed: {error_msg}")
                self._send_error_email(
                    requester_email,
                    "Failed to start picture capture"
                )
            
            # Record request handling metrics
            self.metrics_manager.record_delay(
                source_service='email-handler',
                destination_service='email-handler',
                packet_id=f"handle-{int(start_time)}",
                packet_size=0,
                delay_ms=(time.time() - start_time) * 1000,
                blockchain_enabled=self.blockchain_enabled
            )
            
        except Exception as e:
            print(f"Error handling picture request: {str(e)}")
            self._send_error_email(
                requester_email,
                f"Error processing request: {str(e)}"
            )

    def _send_confirmation_email(self, recipient, subject, message):
        """Send confirmation email with metrics"""
        try:
            start_time = time.time()
            
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.email_address, self.email_password)
                server.send_message(msg)
            
            # Record email sending metrics
            self.metrics_manager.record_delay(
                source_service='email-handler',
                destination_service='email-server',
                packet_id=f"send-{int(start_time)}",
                packet_size=len(message),
                delay_ms=(time.time() - start_time) * 1000,
                blockchain_enabled=self.blockchain_enabled
            )
            
        except Exception as e:
            print(f"Error sending confirmation: {str(e)}")

    def _send_error_email(self, recipient, error_message):
        """Send error notification email"""
        self._send_confirmation_email(
            recipient,
            "Error Processing Request",
            f"An error occurred: {error_message}"
        )

    def run(self):
        """Main service loop with metrics collection"""
        print("Starting email monitoring loop...")
        while True:
            try:
                self.check_emails()
                
                # Record memory and CPU metrics
                self.metrics_manager.record_memory_usage(
                    service_name='email-handler',
                    blockchain_enabled=self.blockchain_enabled
                )
                self.metrics_manager.record_cpu_usage(
                    service_name='email-handler',
                    blockchain_enabled=self.blockchain_enabled
                )
                
                time.sleep(10)
            except Exception as e:
                print(f"Error in main loop: {str(e)}")
                time.sleep(30)

# Flask routes
@app.route('/send_image', methods=['POST'])
def send_image():
    """Handle image sending requests with blockchain verification"""
    try:
        start_time = time.time()
        
        # Verify blockchain signature if enabled
        if app.email_handler.blockchain_enabled:
            signature = request.headers.get('X-Blockchain-Signature')
            if not app.email_handler.blockchain_client.verify_signature(
                request.json,
                signature
            ):
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid blockchain signature'
                }), 401
        
        if 'image' not in request.files:
            return jsonify({'status': 'error', 'message': 'No image file'}), 400
            
        image_file = request.files['image']
        requester_email = request.form.get('requester_email')
        request_id = request.form.get('request_id')
        
        if not requester_email:
            return jsonify({'status': 'error', 'message': 'No requester email'}), 400
        
        # Create email with image
        msg = MIMEMultipart()
        msg['From'] = app.config['EMAIL_ADDRESS']
        msg['To'] = requester_email
        msg['Subject'] = f'Your Requested Camera Image (Request ID: {request_id})'
        
        body = f"""
        Hello,
        
        Here is your requested camera image from request ID: {request_id}.
        This image was captured and sent automatically by the camera system.
        
        Best regards,
        Camera Control System
        """
        msg.attach(MIMEText(body, 'plain'))
        
        # Add image attachment
        image_data = image_file.read()
        image = MIMEImage(image_data)
        filename = image_file.filename or f'camera_image_{request_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jpg'
        image.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(image)
        
        # Send email with retry mechanism
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
                    smtp.login(app.config['EMAIL_ADDRESS'], app.config['EMAIL_PASSWORD'])
                    smtp.send_message(msg)
                    print(f"Successfully sent image email to {requester_email}")
                    break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"Email sending attempt {attempt + 1} failed: {str(e)}")
                time.sleep(retry_delay)
        
        # Record metrics
        app.email_handler.metrics_manager.record_delay(
            source_service='email-handler',
            destination_service='email-server',
            packet_id=f"img-{request_id}",
            packet_size=len(image_data),
            delay_ms=(time.time() - start_time) * 1000,
            blockchain_enabled=app.email_handler.blockchain_enabled
        )
        
        return jsonify({
            'status': 'success',
            'message': f'Image sent to {requester_email}'
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

if __name__ == "__main__":
    # Initialize email handler service
    app.email_handler = EmailHandlerService()
    
    # Store email configuration in app config
    app.config['EMAIL_ADDRESS'] = app.email_handler.email_address
    app.config['EMAIL_PASSWORD'] = app.email_handler.email_password
    
    # Start email monitoring
    app.email_handler.start_monitoring()
    
    # Start Flask server
    print("Starting Email Handler Service...")
    app.run(host='0.0.0.0', port=30082, threaded=True)