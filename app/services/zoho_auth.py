import os
import requests
import time
import logging
from dotenv import load_dotenv
import streamlit as st 

# Load environment variables
load_dotenv()

# Initialize token and expiry
ACCESS_TOKEN = None
TOKEN_EXPIRY = 0  # Unix timestamp

# Environment variables
# REFRESH_TOKEN = os.getenv('REFRESH_TOKEN')
# CLIENT_ID = os.getenv('CLIENT_ID')
# CLIENT_SECRET = os.getenv('CLIENT_SECRET')
# ZOHO_TOKEN_URL = os.getenv('ZOHO_TOKEN_URL')
REFRESH_TOKEN = st.secrets['REFRESH_TOKEN']
CLIENT_ID = st.secrets['CLIENT_ID']
CLIENT_SECRET = st.secrets['CLIENT_SECRET']
ZOHO_TOKEN_URL = st.secrets['ZOHO_TOKEN_URL']


# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class ZohoAuthError(Exception):
    """Base exception for Zoho authentication errors"""
    pass

class ZohoTokenError(ZohoAuthError):
    """Exception raised for token-related errors"""
    pass

class ZohoRateLimitError(ZohoAuthError):
    """Exception raised when rate limit is exceeded"""
    pass

def get_access_token():
    """
    Retrieve a valid Zoho access token using the refresh token. Handles token expiry and logs errors gracefully.
    
    Returns:
        str: Valid access token
        
    Raises:
        ZohoTokenError: For invalid or expired refresh tokens
        ZohoRateLimitError: When API rate limits are exceeded
        ZohoAuthError: For other authentication-related errors
    """
    global ACCESS_TOKEN, TOKEN_EXPIRY

    # Reuse token if not expired
    if ACCESS_TOKEN and time.time() < TOKEN_EXPIRY - 60:
        return ACCESS_TOKEN

    # Validate required credentials
    if not all([REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET, ZOHO_TOKEN_URL]):
        error_msg = "Missing one or more required Zoho authentication environment variables."
        logging.error(error_msg)
        raise ZohoAuthError(error_msg)

    try:
        # Request new access token
        response = requests.post(ZOHO_TOKEN_URL, params={
            "refresh_token": REFRESH_TOKEN,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token"
        }, timeout=10)  # Add timeout to prevent hanging

        # Handle rate limiting (Zoho typically uses 429 for rate limits)
        if response.status_code == 429:
            error_msg = "Zoho API rate limit reached. Please try again later."
            logging.error(error_msg)
            raise ZohoRateLimitError(error_msg)
            
        # Handle invalid/expired refresh token (Zoho typically uses 400 for this)
        if response.status_code == 400:
            error_msg = "Invalid or expired Zoho refresh token. Please check your credentials."
            logging.error(f"{error_msg} Response: {response.text}")
            raise ZohoTokenError(error_msg)
            
        # Handle other error status codes
        if response.status_code != 200:
            error_msg = f"Failed to refresh access token. Status: {response.status_code}"
            logging.error(f"{error_msg} Response: {response.text}")
            raise ZohoAuthError(error_msg)

        # Success
        try:
            data = response.json()
            if 'access_token' not in data:
                error_msg = "No access token in Zoho API response"
                logging.error(f"{error_msg}. Response: {data}")
                raise ZohoAuthError(error_msg)
                
            ACCESS_TOKEN = data['access_token']
            TOKEN_EXPIRY = time.time() + data.get('expires_in', 3600)
            logging.info("Access token successfully refreshed.")
            return ACCESS_TOKEN
            
        except (ValueError, KeyError) as e:
            error_msg = f"Invalid response format from Zoho API: {str(e)}"
            logging.error(f"{error_msg} Response: {response.text}")
            raise ZohoAuthError(error_msg) from e

    except requests.Timeout:
        error_msg = "Request to Zoho API timed out. Please check your network connection."
        logging.error(error_msg)
        raise ZohoAuthError(error_msg)
        
    except requests.RequestException as e:
        error_msg = f"Network error while requesting access token: {str(e)}"
        logging.exception(error_msg)
        raise ZohoAuthError(error_msg) from e
        
    except Exception as e:
        error_msg = f"Unexpected error during token retrieval: {str(e)}"
        logging.exception(error_msg)
        raise ZohoAuthError(error_msg) from e



