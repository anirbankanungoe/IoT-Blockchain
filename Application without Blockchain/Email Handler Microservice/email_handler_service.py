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

app = Flask(__name__)

class EmailHandlerService:
    def __init__(self):
        # Email configuration
        self.email_address = os.getenv('EMAIL_ADDRESS', 'picturecontroller@gmail.com')
        self.email_password = os.getenv('EMAIL_PASSWORD', 'yjtsnspdcgpqhbjd')
        self.imap_server = "imap.gmail.com"
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 465  # SSL port
        
        # Image DB service URL using ZeroTier IP
        self.db_service_url = os.getenv('DB_SERVICE_URL', 'http://172.23.228.240:30081')
        
        print(f"Email Handler Service initialized with:")
        print(f"Email: {self.email_address}")
        print(f"DB Service URL: {self.db_service_url}")

    def start_monitoring(self):
        """Start email monitoring in a separate thread."""
        monitor_thread = threading.Thread(target=self.run)
        monitor_thread.daemon = True
        monitor_thread.start()

    def check_emails(self):
        """Check for new emails requesting pictures."""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.email_password)
            mail.select('inbox')
            
            # Search for unread emails
            _, messages = mail.search(None, 'UNSEEN')
            
            for num in messages[0].split():
                _, msg = mail.fetch(num, '(RFC822)')
                email_body = msg[0][1]
                email_message = email.message_from_bytes(email_body)
                
                # Get sender email
                sender = email.utils.parseaddr(email_message['from'])[1]
                subject = email_message['subject'] or ''
                
                # Get email body
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
                print(f"Body: {body[:100]}...")  # Log first 100 chars of body
                
                # Process commands
                if 'send pictures for 2 minutes' in body.lower():
                    print(f"Received picture request from {sender}")
                    self._handle_picture_request(sender)
                elif 'give latest status' in subject.lower():
                    print(f"Received status request from {sender}")
                    self._handle_status_request(sender)
                
                # Mark as read
                mail.store(num, '+FLAGS', '\\Seen')
            
            mail.logout()
            
        except Exception as e:
            print(f"Error checking emails: {str(e)}")

    def _handle_picture_request(self, requester_email):
        """Handle request for pictures."""
        try:
            print(f"Sending capture request to DB service for {requester_email}")
            response = requests.post(
                f"{self.db_service_url}/start_capture",
                json={
                    'requester_email': requester_email,
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            if response.status_code == 200:
                print("Capture request successful")
                self._send_confirmation_email(
                    requester_email,
                    "Picture capture started",
                    "Your request for pictures has been received. Images will be sent shortly."
                )
            else:
                print(f"Capture request failed: {response.text}")
                self._send_error_email(
                    requester_email,
                    "Failed to start picture capture"
                )
                
        except Exception as e:
            print(f"Error handling picture request: {str(e)}")
            self._send_error_email(
                requester_email,
                f"Error processing request: {str(e)}"
            )

    def _handle_status_request(self, requester_email):
        """Handle request for latest status."""
        try:
            response = requests.get(f"{self.db_service_url}/health")
            
            if response.status_code == 200:
                self._send_confirmation_email(
                    requester_email,
                    "System Status",
                    "All systems are operational and ready to process requests."
                )
            else:
                self._send_error_email(
                    requester_email,
                    "System status check failed"
                )
                
        except Exception as e:
            print(f"Error handling status request: {str(e)}")
            self._send_error_email(
                requester_email,
                f"Error checking status: {str(e)}"
            )

    def _send_confirmation_email(self, recipient, subject, message):
        """Send confirmation email."""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.email_address, self.email_password)
                server.send_message(msg)
                print(f"Sent confirmation email to {recipient}")
                
        except Exception as e:
            print(f"Error sending confirmation: {str(e)}")

    def _send_error_email(self, recipient, error_message):
        """Send error notification email."""
        self._send_confirmation_email(
            recipient,
            "Error Processing Request",
            f"An error occurred: {error_message}"
        )

    def run(self):
        """Main service loop."""
        print("Starting email monitoring loop...")
        while True:
            try:
                self.check_emails()
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                print(f"Error in main loop: {str(e)}")
                time.sleep(30)  # Wait longer on error

# Flask routes
@app.route('/send_image', methods=['POST'])
def send_image():
    """Handle image sending requests from Image DB Service."""
    try:
        if 'image' not in request.files:
            print("No image file in request")
            return jsonify({'status': 'error', 'message': 'No image file'}), 400
            
        image_file = request.files['image']
        requester_email = request.form.get('requester_email')
        request_id = request.form.get('request_id')
        
        if not requester_email:
            print("No requester email provided")
            return jsonify({'status': 'error', 'message': 'No requester email'}), 400
            
        print(f"Received image for request {request_id} to send to {requester_email}")
        
        try:
            # Create email with image
            msg = MIMEMultipart()
            msg['From'] = app.config['EMAIL_ADDRESS']
            msg['To'] = requester_email
            msg['Subject'] = f'Your Requested Camera Image (Request ID: {request_id})'
            
            # Add message body with more information
            body = f"""
            Hello,
            
            Here is your requested camera image from request ID: {request_id}.
            This image was captured and sent automatically by the camera system.
            
            Best regards,
            Camera Control System
            """
            msg.attach(MIMEText(body, 'plain'))
            
            # Add image attachment with proper filename
            image_data = image_file.read()
            image = MIMEImage(image_data)
            # Use the original filename or create one if not available
            filename = image_file.filename or f'camera_image_{request_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jpg'
            image.add_header('Content-Disposition', 'attachment', filename=filename)
            image.add_header('Content-ID', f'<{filename}>')
            msg.attach(image)
            
            # Send email with retry mechanism
            max_retries = 3
            retry_delay = 2  # seconds
            
            for attempt in range(max_retries):
                try:
                    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
                        smtp.login(app.config['EMAIL_ADDRESS'], app.config['EMAIL_PASSWORD'])
                        smtp.send_message(msg)
                        print(f"Successfully sent image email to {requester_email} (Attempt {attempt + 1})")
                        break
                except Exception as e:
                    if attempt == max_retries - 1:  # Last attempt
                        raise
                    print(f"Email sending attempt {attempt + 1} failed: {str(e)}. Retrying...")
                    time.sleep(retry_delay)
            
            return jsonify({
                'status': 'success',
                'message': f'Image sent to {requester_email}',
                'filename': filename
            }), 200
            
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error sending email: {str(e)}"
            print(error_msg)
            return jsonify({
                'status': 'error',
                'message': error_msg
            }), 500
            
        except Exception as e:
            error_msg = f"Error creating/sending email: {str(e)}"
            print(error_msg)
            return jsonify({
                'status': 'error',
                'message': error_msg
            }), 500
            
    except Exception as e:
        error_msg = f"Error processing image send request: {str(e)}"
        print(error_msg)
        return jsonify({
            'status': 'error',
            'message': error_msg
        }), 500
        
    except Exception as e:
        print(f"Error sending image: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

if __name__ == "__main__":
    # Initialize email service
    email_service = EmailHandlerService()
    
    # Verify email credentials
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as smtp:
            smtp.login(email_service.email_address, email_service.email_password)
            print("Email credentials verified successfully")
    except Exception as e:
        print(f"ERROR: Failed to verify email credentials: {str(e)}")
        sys.exit(1)
    
    # Store email configuration in app config
    app.config['EMAIL_ADDRESS'] = email_service.email_address
    app.config['EMAIL_PASSWORD'] = email_service.email_password
    
    # Start email monitoring in background
    email_service.start_monitoring()
    
    # Start Flask server
    print("Starting Flask server on ZeroTier network...")
    app.run(host='0.0.0.0', port=30082, threaded=True)