import requests
import logging
import time
from typing import List, Dict, Optional, Any
from .zoho_auth import get_access_token, ZohoTokenError, ZohoRateLimitError
import os
import streamlit as st

class ZohoAPIError(Exception):
    """Base exception for Zoho API errors"""
    pass

class ZohoNoDataError(ZohoAPIError):
    """Exception raised when no data is found"""
    pass


class ZohoJobService:
    """Service for interacting with Zoho Recruit job openings"""

    def __init__(self):
        # self.base_url = os.getenv("ZOHO_RECRUIT_BASE_API_URL")
        self.base_url = st.secrets ["ZOHO_RECRUIT_BASE_API_URL"]

        self.jobs_endpoint = f"{self.base_url}/JobOpenings"

    def _make_api_request(self, url: str, params: Optional[Dict] = None, max_retries: int = 3) -> Dict[str, Any]:
        """
        Make an API request with retry logic and proper error handling.
        
        Args:
            url: The API endpoint URL
            params: Query parameters for the request
            max_retries: Maximum number of retry attempts
            
        Returns:
            dict: The JSON response from the API
            
        Raises:
            ZohoAPIError: For API-related errors
            ZohoRateLimitError: When rate limits are exceeded
            ZohoTokenError: For authentication failures
        """
        retry_delay = 2  # Initial delay in seconds
        
        for attempt in range(max_retries + 1):
            try:
                access_token = get_access_token()
                headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
                
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=30  # 30 second timeout
                )
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))  # Default to 60 seconds if header not present
                    if attempt < max_retries:
                        logging.warning(f"Rate limited. Retrying after {retry_after} seconds (attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_after)
                        continue
                    raise ZohoRateLimitError(
                        f"Zoho API rate limit reached after {max_retries} attempts. "
                        f"Please try again later or increase rate limits in your Zoho account."
                    )
                
                # Handle unauthorized/forbidden (likely token issues)
                if response.status_code in (401, 403):
                    raise ZohoTokenError("Authentication failed. The access token may be invalid or expired.")
                
                # Handle other errors
                response.raise_for_status()
                
                return response.json()
                
            except requests.Timeout as e:
                if attempt == max_retries:
                    raise ZohoAPIError("Request to Zoho API timed out. Please check your network connection.") from e
                logging.warning(f"Request timeout (attempt {attempt + 1}/{max_retries}). Retrying...")
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                
            except requests.RequestException as e:
                if attempt == max_retries:
                    raise ZohoAPIError(f"Failed to fetch data from Zoho API: {str(e)}") from e
                logging.warning(f"Request failed (attempt {attempt + 1}/{max_retries}). Retrying...")
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
        
        # Should never reach here due to the raises in the loop
        raise ZohoAPIError("Failed to complete API request after multiple attempts")

    def get_active_job_openings(self, per_page: int = 200) -> List[Dict[str, str]]:
        """
        Fetch all approved and in-progress job openings from Zoho Recruit using pagination.

        Args:
            per_page: Number of jobs to fetch per page (default is 200)

        Returns:
            List of dict: List of filtered job openings with id, title, and description.

        Raises:
            ZohoAPIError: For API-related errors
            ZohoRateLimitError: When rate limits are exceeded
            ZohoTokenError: For authentication failures
            ZohoNoDataError: When no matching job openings are found
        """
        all_jobs = []
        page = 1
        total_pages = None

        try:
            while True:
                try:
                    params = {
                        "per_page": per_page,
                        "page": page,
                    }

                    jobs_data = self._make_api_request(self.jobs_endpoint, params=params)
                    job_entries = jobs_data.get("data", [])

                    if total_pages is None and 'page_context' in jobs_data:
                        total_pages = jobs_data['page_context'].get('total_pages', 1)

                    current_batch = []
                    for job in job_entries:
                        job_id = job.get("id")
                        job_title = job.get("Posting_Title")
                        job_desc = job.get("Job_Description")

                        # ✅ Apply filters
                        job_status = job.get("Job_Opening_Status")
                        approval_state = job.get("$approval_state")

                        if job_status != "In-progress" or approval_state != "approved":
                            continue

                        if not all([job_id, job_title]):
                            logging.warning(f"Skipping incomplete job entry: {job}")
                            continue

                        current_batch.append({
                            "id": job_id,
                            "title": job_title,
                            "description": job_desc or "No description available"
                        })

                    all_jobs.extend(current_batch)
                    logging.info(f"Fetched page {page}{f'/{total_pages}' if total_pages else ''} "
                                f"with {len(current_batch)} filtered jobs. Total so far: {len(all_jobs)}")

                    if len(job_entries) < per_page or (total_pages and page >= total_pages):
                        break

                    page += 1

                except (ZohoRateLimitError, ZohoTokenError, ZohoAPIError):
                    raise

                except Exception as e:
                    logging.exception(f"Unexpected error processing job openings: {str(e)}")
                    raise ZohoAPIError(f"Failed to process job openings: {str(e)}") from e

            if not all_jobs:
                raise ZohoNoDataError("No active approved job openings found in Zoho Recruit.")

            return all_jobs

        except Exception as e:
            if not isinstance(e, (ZohoAPIError, ZohoTokenError, ZohoRateLimitError)):
                logging.exception("Unexpected error in get_active_job_openings")
                raise ZohoAPIError(f"Failed to fetch job openings: {str(e)}") from e
            raise




