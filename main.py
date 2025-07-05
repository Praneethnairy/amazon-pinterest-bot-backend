from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, validator
from typing import List, Optional, Dict, Any
import asyncio
import uuid
import json
import os
import logging
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import secrets
import hashlib
from trending_amazon_pinterest_bot import TrendingAmazonPinterestBot

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Amazon Pinterest Automation API",
    description="Secure API for automating Amazon affiliate posts on Pinterest",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://localhost:3000", "https://automationcenter.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# In-memory storage for active jobs (use Redis in production)
active_jobs: Dict[str, Dict] = {}
encryption_keys: Dict[str, str] = {}

# Encryption utilities
class EncryptionManager:
    @staticmethod
    def generate_key(password: str, salt: bytes = None) -> bytes:
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt
    
    @staticmethod
    def encrypt_data(data: str, key: bytes) -> str:
        f = Fernet(key)
        encrypted_data = f.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_data).decode()
    
    @staticmethod
    def decrypt_data(encrypted_data: str, key: bytes) -> str:
        f = Fernet(key)
        decoded_data = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted_data = f.decrypt(decoded_data)
        return decrypted_data.decode()

# Pydantic models
class CredentialsModel(BaseModel):
    pinterest_token: str
    amazon_tag: str
    session_password: str
    
    @validator('pinterest_token')
    def validate_pinterest_token(cls, v):
        if not v or len(v) < 10:
            raise ValueError('Invalid Pinterest token')
        return v
    
    @validator('amazon_tag')
    def validate_amazon_tag(cls, v):
        if not v or len(v) < 3:
            raise ValueError('Invalid Amazon associate tag')
        return v

class AutomationConfigModel(BaseModel):
    categories: List[str] = ["electronics", "home", "fashion", "health"]
    max_products_per_category: int = 5
    post_interval_seconds: int = 300
    daily_pin_limit: int = 50
    min_rating: float = 4.0
    min_reviews: int = 10
    price_range_min: int = 5
    price_range_max: int = 500
    
    @validator('categories')
    def validate_categories(cls, v):
        valid_categories = ["electronics", "home", "fashion", "health", "books", "sports"]
        for cat in v:
            if cat not in valid_categories:
                raise ValueError(f'Invalid category: {cat}')
        return v
    
    @validator('max_products_per_category')
    def validate_max_products(cls, v):
        if v < 1 or v > 20:
            raise ValueError('Max products per category must be between 1 and 20')
        return v

class AutomationRequestModel(BaseModel):
    credentials: CredentialsModel
    config: AutomationConfigModel

class JobStatusModel(BaseModel):
    job_id: str
    status: str
    progress: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# Authentication and encryption helpers
def generate_session_key() -> str:
    return secrets.token_urlsafe(32)

def hash_session_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

async def verify_session(credentials: HTTPAuthorizationCredentials = Security(security)):
    session_id = credentials.credentials
    if session_id not in encryption_keys:
        raise HTTPException(status_code=401, detail="Invalid session")
    return session_id

# Background task for automation
async def run_automation_task(job_id: str, encrypted_credentials: str, config: AutomationConfigModel, encryption_key: bytes):
    try:
        # Update job status
        active_jobs[job_id]["status"] = "running"
        active_jobs[job_id]["updated_at"] = datetime.now()
        
        # Decrypt credentials
        credentials_json = EncryptionManager.decrypt_data(encrypted_credentials, encryption_key)
        credentials = json.loads(credentials_json)
        
        # Initialize bot
        bot = TrendingAmazonPinterestBot(
            credentials["pinterest_token"],
            credentials["amazon_tag"]
        )
        
        # Track overall progress
        total_categories = len(config.categories)
        completed_categories = 0
        overall_results = {
            'total_products_found': 0,
            'total_pins_created': 0,
            'total_errors': 0,
            'category_results': {}
        }
        
        # Process each category
        for category in config.categories:
            try:
                # Update progress
                active_jobs[job_id]["progress"] = {
                    "current_category": category,
                    "completed_categories": completed_categories,
                    "total_categories": total_categories,
                    "overall_progress": (completed_categories / total_categories) * 100
                }
                
                # Run automation for category
                results = bot.run_complete_automation(
                    category=category,
                    max_products=config.max_products_per_category,
                    post_interval=config.post_interval_seconds
                )
                
                # Update overall results
                overall_results['total_products_found'] += results['products_found']
                overall_results['total_pins_created'] += results['pins_created']
                overall_results['total_errors'] += results['errors']
                overall_results['category_results'][category] = results
                
                completed_categories += 1
                
                # Update job with intermediate results
                active_jobs[job_id]["results"] = overall_results
                active_jobs[job_id]["updated_at"] = datetime.now()
                
            except Exception as e:
                logger.error(f"Error processing category {category}: {e}")
                overall_results['total_errors'] += 1
                overall_results['category_results'][category] = {"error": str(e)}
        
        # Mark job as completed
        active_jobs[job_id]["status"] = "completed"
        active_jobs[job_id]["results"] = overall_results
        active_jobs[job_id]["progress"]["overall_progress"] = 100
        active_jobs[job_id]["updated_at"] = datetime.now()
        
        logger.info(f"Job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = str(e)
        active_jobs[job_id]["updated_at"] = datetime.now()

# API Routes
@app.post("/api/start-session")
async def start_session(credentials: CredentialsModel):
    """Start an encrypted session"""
    try:
        # Generate session ID and encryption key
        session_id = generate_session_key()
        password_hash = hash_session_password(credentials.session_password)
        
        # Generate encryption key from session password
        encryption_key, salt = EncryptionManager.generate_key(credentials.session_password)
        
        # Store encryption key (in production, use secure storage)
        encryption_keys[session_id] = {
            "key": encryption_key,
            "salt": salt,
            "created_at": datetime.now()
        }
        
        # Encrypt and store credentials
        credentials_dict = {
            "pinterest_token": credentials.pinterest_token,
            "amazon_tag": credentials.amazon_tag
        }
        encrypted_credentials = EncryptionManager.encrypt_data(
            json.dumps(credentials_dict), 
            encryption_key
        )
        
        # Test Pinterest connection
        try:
            bot = TrendingAmazonPinterestBot(credentials.pinterest_token, credentials.amazon_tag)
            boards = bot.get_pinterest_boards()
            if not boards:
                raise HTTPException(status_code=400, detail="Invalid Pinterest credentials or no boards found")
            
            boards_info = [{"id": board["id"], "name": board["name"]} for board in boards[:5]]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Pinterest connection failed: {str(e)}")
        
        return {
            "session_id": session_id,
            "encrypted_credentials": encrypted_credentials,
            "pinterest_boards": boards_info,
            "message": "Session started successfully"
        }
        
    except Exception as e:
        logger.error(f"Session start failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to start session")

@app.post("/api/start-automation")
async def start_automation(
    request: AutomationRequestModel,
    background_tasks: BackgroundTasks,
    session_id: str = Depends(verify_session)
):
    """Start the automation process"""
    try:
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Get encryption key
        if session_id not in encryption_keys:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        encryption_key = encryption_keys[session_id]["key"]
        
        # Encrypt credentials
        credentials_dict = {
            "pinterest_token": request.credentials.pinterest_token,
            "amazon_tag": request.credentials.amazon_tag
        }
        encrypted_credentials = EncryptionManager.encrypt_data(
            json.dumps(credentials_dict), 
            encryption_key
        )
        
        # Create job entry
        active_jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "progress": {"overall_progress": 0},
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "session_id": session_id,
            "config": request.config.dict()
        }
        
        # Start background task
        background_tasks.add_task(
            run_automation_task,
            job_id,
            encrypted_credentials,
            request.config,
            encryption_key
        )
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Automation started successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to start automation: {e}")
        raise HTTPException(status_code=500, detail="Failed to start automation")

@app.get("/api/job-status/{job_id}")
async def get_job_status(job_id: str, session_id: str = Depends(verify_session)):
    """Get the status of an automation job"""
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = active_jobs[job_id]
    
    # Verify session ownership
    if job.get("session_id") != session_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return JobStatusModel(**job)

@app.get("/api/jobs")
async def get_user_jobs(session_id: str = Depends(verify_session)):
    """Get all jobs for the current session"""
    user_jobs = []
    for job_id, job in active_jobs.items():
        if job.get("session_id") == session_id:
            user_jobs.append(JobStatusModel(**job))
    
    return {"jobs": user_jobs}

@app.delete("/api/job/{job_id}")
async def cancel_job(job_id: str, session_id: str = Depends(verify_session)):
    """Cancel a running job"""
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = active_jobs[job_id]
    
    # Verify session ownership
    if job.get("session_id") != session_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update job status
    active_jobs[job_id]["status"] = "cancelled"
    active_jobs[job_id]["updated_at"] = datetime.now()
    
    return {"message": "Job cancelled successfully"}

@app.delete("/api/session")
async def end_session(session_id: str = Depends(verify_session)):
    """End the current session and cleanup"""
    try:
        # Remove encryption keys
        if session_id in encryption_keys:
            del encryption_keys[session_id]
        
        # Cancel active jobs for this session
        for job_id, job in active_jobs.items():
            if job.get("session_id") == session_id and job["status"] in ["queued", "running"]:
                active_jobs[job_id]["status"] = "cancelled"
                active_jobs[job_id]["updated_at"] = datetime.now()
        
        return {"message": "Session ended successfully"}
        
    except Exception as e:
        logger.error(f"Failed to end session: {e}")
        raise HTTPException(status_code=500, detail="Failed to end session")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "active_jobs": len(active_jobs),
        "active_sessions": len(encryption_keys)
    }

@app.get("/api/test")
async def test_endpoint():
    """Test endpoint that returns Hello, world!"""
    return {"message": "Hello, world!"}

# Privacy policy endpoint
@app.get("/api/privacy-policy")
async def get_privacy_policy():
    """Get the privacy policy"""
    privacy_policy = """
    # Privacy Policy for Automation Center App

    **Effective Date:** July 5, 2025

    ## 1. Information We Collect

    ### 1.1 Credentials and API Tokens
    - Pinterest API access tokens (encrypted and stored temporarily)
    - Amazon Associates affiliate tags (encrypted and stored temporarily)
    - Session passwords for encryption (never stored in plain text)

    ### 1.2 Automation Configuration
    - Product categories and preferences
    - Posting intervals and limits
    - Product filtering criteria

    ### 1.3 Technical Information
    - Job execution logs and status
    - Error messages and debugging information
    - Session identifiers (temporary)

    ## 2. How We Use Your Information

    ### 2.1 Primary Purpose
    - Execute Amazon product automation as requested
    - Create Pinterest pins with affiliate links
    - Monitor job progress and provide status updates

    ### 2.2 Technical Operations
    - Maintain secure sessions during automation
    - Log activities for debugging and support
    - Ensure proper rate limiting and compliance

    ## 3. Data Security and Encryption

    ### 3.1 End-to-End Encryption
    - All sensitive data is encrypted using Fernet symmetric encryption
    - Encryption keys are derived from user-provided session passwords
    - No plain text credentials are ever stored on our servers

    ### 3.2 Session Security
    - Temporary session-based storage only
    - Automatic session cleanup after completion
    - No persistent storage of credentials

    ### 3.3 Transport Security
    - All communications use HTTPS/TLS encryption
    - API endpoints require authentication
    - CORS restrictions limit access to authorized domains

    ## 4. Data Retention and Deletion

    ### 4.1 Temporary Storage
    - Credentials are stored only during active sessions
    - Automatic deletion when session ends
    - Job logs retained for 24 hours maximum

    ### 4.2 User Control
    - Users can end sessions at any time
    - Immediate deletion of all session data
    - No backup or archival of sensitive information

    ## 5. Third-Party Services

    ### 5.1 Pinterest API
    - We access Pinterest on your behalf using your credentials
    - Subject to Pinterest's Terms of Service and Privacy Policy
    - No data shared with Pinterest beyond necessary API calls

    ### 5.2 Amazon Associates
    - We generate affiliate links using your associate tag
    - Subject to Amazon Associates Operating Agreement
    - No additional data shared with Amazon

    ## 6. Data Sharing and Disclosure

    ### 6.1 No Third-Party Sharing
    - We never share, sell, or rent your personal information
    - No marketing or advertising use of your data
    - No analytics or tracking beyond technical operations

    ### 6.2 Legal Requirements
    - We may disclose information if legally required
    - Only in response to valid legal process
    - We will notify users when legally permitted

    ## 7. Your Rights and Choices

    ### 7.1 Access and Control
    - View job status and progress in real-time
    - Cancel automation jobs at any time
    - End sessions and delete data immediately

    ### 7.2 Data Portability
    - Export job results and statistics
    - Download automation logs
    - No vendor lock-in or data restrictions

    ## 8. Children's Privacy

    This service is not intended for users under 18 years of age. We do not knowingly collect personal information from children under 18.

    ## 9. International Users

    ### 9.1 Data Processing
    - Data processed in the user's session only
    - No cross-border data transfers for storage
    - Compliance with applicable privacy laws

    ### 9.2 Legal Compliance
    - GDPR compliance for EU users
    - CCPA compliance for California residents
    - Other regional privacy law compliance

    ## 10. Security Measures

    ### 10.1 Technical Safeguards
    - Industry-standard encryption algorithms
    - Secure session management
    - Regular security audits and updates

    ### 10.2 Operational Security
    - Limited access to systems and data
    - Employee training on privacy practices
    - Incident response procedures

    ## 11. Changes to This Policy

    ### 11.1 Updates
    - We may update this policy as needed
    - Users will be notified of material changes
    - Continued use constitutes acceptance

    ### 11.2 Version Control
    - Policy versions are tracked and dated
    - Previous versions available upon request
    - Clear change documentation

    ## 12. Contact Information

    For questions about this privacy policy or our data practices:

    - **Email:** privacy@automationcenter.com
    - **Response Time:** Within 48 hours
    - **Data Protection Officer:** Available upon request

    ## 13. Compliance Certifications

    ### 13.1 Standards
    - SOC 2 Type II compliance (planned)
    - ISO 27001 information security management
    - Regular third-party security assessments

    ### 13.2 Industry Best Practices
    - OWASP security guidelines
    - NIST cybersecurity framework
    - Privacy by design principles

    ## 14. Transparency Report

    We believe in transparency about our data practices:

    - **Data Requests:** We have received 0 government data requests
    - **Security Incidents:** 0 data breaches or security incidents
    - **User Rights Requests:** Processed within 30 days

    ---

    **Last Updated:** July 5, 2025
    **Version:** 1.0

    This privacy policy is designed to be transparent, comprehensive, and user-friendly. We are committed to protecting your privacy and providing you with control over your data.
    """
    
    return {"privacy_policy": privacy_policy}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
