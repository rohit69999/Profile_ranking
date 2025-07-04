import os
import requests
import logging
import tempfile
import asyncio
import aiohttp
import time
from typing import List, Dict, Optional
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log
)
from .zoho_auth import get_access_token
from .fetch_openings import ZohoJobService
from ..exceptions import ZohoRateLimitError

# Configure logging
logger = logging.getLogger(__name__)

class ZohoCandidateService:
    """Optimized service for downloading resumes with rate limit handling."""

    def __init__(self, max_concurrent_downloads: int = 20):
        """
        Initialize with safe defaults.
        
        Args:
            max_concurrent_downloads: Recommended 10-15 for most accounts
        """
        # self.base_url = os.getenv("ZOHO_RECRUIT_BASE_API_URL")
        self.base_url = st.secrets["ZOHO_RECRUIT_BASE_API_URL"]
        if not self.base_url:
            raise ValueError("ZOHO_RECRUIT_BASE_API_URL environment variable not set")
        
        self.job_service = ZohoJobService()
        self.temp_dir = None
        self.max_concurrent_downloads = max_concurrent_downloads
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        
        # Rate limit tracking
        self.request_count = 0
        self.last_reset_time = time.time()
        self.rate_limit = 100  # Zoho's limit per minute
        self.safety_buffer = 5  # Stay 5 requests under limit
        
        # Track failed downloads
        self.failed_downloads = []
        

    def create_temp_dir(self) -> str:
        """Create secure temp directory for downloads."""
        self.temp_dir = tempfile.mkdtemp(prefix="zoho_resumes_")
        logger.info(f"Created temp directory: {self.temp_dir}")
        return self.temp_dir

    def get_failed_downloads(self):
        """Get list of failed downloads with reasons"""
        return self.failed_downloads
        
    def cleanup_temp_dir(self):
        """Clean up temporary files safely."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                for filename in os.listdir(self.temp_dir):
                    file_path = os.path.join(self.temp_dir, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except Exception as e:
                        logger.error(f"Error deleting {file_path}: {str(e)}")
                os.rmdir(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
            except Exception as e:
                logger.error(f"Temp directory cleanup failed: {str(e)}")

    async def _check_rate_limit(self):
        """Enforce 100 requests per minute limit."""
        now = time.time()
        elapsed = now - self.last_reset_time
        
        if elapsed >= 60:  # Reset counter every minute
            self.request_count = 0
            self.last_reset_time = now
            return
            
        remaining = self.rate_limit - self.request_count
        if remaining <= self.safety_buffer:
            wait_time = 60 - elapsed
            logger.warning(
                f"Approaching rate limit ({self.request_count}/100). "
                f"Waiting {wait_time:.1f} seconds..."
            )
            await asyncio.sleep(wait_time)
            self.request_count = 0
            self.last_reset_time = time.time()

    @retry(
        retry=retry_if_exception_type((ZohoRateLimitError, aiohttp.ClientError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=5, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def _download_resume_async(
        self,
        session: aiohttp.ClientSession,
        candidate: Dict,
        headers: Dict
    ) -> Optional[str]:
        """
        Download a single resume with rate limit handling.
        
        Returns:
            Path to downloaded file or None if failed
        """
        await self._check_rate_limit()
        
        candidate_id = candidate["id"]
        candidate_name = candidate.get("Full_Name", "Unknown")
        safe_name = "".join(c for c in candidate_name if c.isalnum() or c in (' ', '_')).rstrip()
        
        try:
            # Request 1: List attachments
            self.request_count += 1
            attachments_url = f"{self.base_url}/Candidates/{candidate_id}/attachments"
            
            async with session.get(
                attachments_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 429:
                    retry_after = int(response.headers.get('Retry-After', 30))
                    logger.warning(f"Rate limited. W    aiting {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    raise ZohoRateLimitError("Rate limit exceeded")
                
                response.raise_for_status()
                attachments = (await response.json()).get("data", [])
                
                # Find first valid resume file
                for attachment in attachments:
                    file_name = attachment.get("File_Name", "").lower()
                    if any(file_name.endswith(ext) for ext in (".pdf", ".docx", ".doc")):
                        file_id = attachment["id"]
                        break
                else:
                    logger.warning(f"No resume found for {safe_name}")
                    return None

            # Request 2: Download file
            self.request_count += 1
            download_url = f"{self.base_url}/Candidates/{candidate_id}/attachments/{file_id}"
            
            async with session.get(
                download_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                response.raise_for_status()
                
                if not self.temp_dir:
                    self.create_temp_dir()
                
                ext = os.path.splitext(file_name)[1]
                filename = f"{safe_name}_{candidate_id}{ext}"
                filepath = os.path.join(self.temp_dir, filename)
                
                # Stream download to handle large files
                with open(filepath, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                
                logger.info(f"✅ Downloaded: {filename}")
                return filepath
                
        except Exception as e:
            error_msg = str(e) or "Unknown error"
            logger.error(f"❌ Failed to download for {safe_name}: {error_msg}")
            self.failed_downloads.append({
                "name": safe_name,
                "error": error_msg,
                "candidate_id": candidate_id
            })
            raise

    async def _download_with_semaphore(
        self,
        session: aiohttp.ClientSession,
        candidate: Dict,
        headers: Dict
    ) -> Optional[str]:
        """Limit concurrent downloads using semaphore."""
        async with self.semaphore:
            return await self._download_resume_async(session, candidate, headers)

    async def download_resumes_async(
        self,
        candidates: List[Dict],
        headers: Dict,
        progress_callback=None
    ) -> List[str]:
        """
        Download resumes in parallel with rate limit control.
        
        Args:
            candidates: List of candidate dicts with 'id' and 'Full_Name'
            headers: Auth headers
            progress_callback: Optional function(current, total)
            
        Returns:
            List of downloaded file paths
        """
        if not candidates:
            return []
            
        if not self.temp_dir:
            self.create_temp_dir()
        
        downloaded_files = []
        total = len(candidates)
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for candidate in candidates:
                task = asyncio.create_task(
                    self._download_with_semaphore(session, candidate, headers)
                )
                task.add_done_callback(
                    lambda f, c=candidate: self._handle_download_result(
                        f, c, downloaded_files, progress_callback, total
                    )
                )
                tasks.append(task)
            
            await asyncio.gather(*tasks, return_exceptions=True)
        
        return downloaded_files

    def _handle_download_result(
        self,
        future,
        candidate,
        downloaded_files,
        progress_callback,
        total
    ):
        """Process completed download tasks."""
        try:
            result = future.result()
            if result:
                downloaded_files.append(result)
        except Exception as e:
            logger.error(
                f"Failed to download resume for {candidate.get('Full_Name', 'Unknown')}: {str(e)}"
            )
        
        if progress_callback:
            progress_callback(len(downloaded_files), total)

    def download_resumes_sync(
        self,
        candidates: List[Dict],
        headers: Dict,
        progress_callback=None
    ) -> List[str]:
        """Synchronous wrapper for async download."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(
            self.download_resumes_async(candidates, headers, progress_callback)
        )

    def batch_download_resumes(
        self,
        candidates: List[Dict],
        batch_size: int = 50,
        delay: int = 65
    ) -> List[str]:
        """
        Process candidates in batches with delays to respect rate limits.
        
        Args:
            candidates: List of candidate dicts
            batch_size: Candidates per batch (default 50 = 100 API calls)
            delay: Seconds between batches (default 65 for safety)
            
        Returns:
            List of all successfully downloaded file paths
        """
        headers = {"Authorization": f"Zoho-oauthtoken {get_access_token()}"}
        all_downloads = []
        
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} ({len(batch)} candidates)")
            
            downloaded = self.download_resumes_sync(batch, headers)
            all_downloads.extend(downloaded)
            
            if i + batch_size < len(candidates):
                logger.info(f"Waiting {delay} seconds before next batch...")
                time.sleep(delay)
        
        return all_downloads

    def fetch_and_download_all(self):
        """Complete workflow: fetch jobs -> candidates -> download resumes."""
        try:
            self.create_temp_dir()
            headers = {"Authorization": f"Zoho-oauthtoken {get_access_token()}"}
            
            # Get active jobs
            jobs = self.job_service.get_active_job_openings()
            logger.info(f"Found {len(jobs)} active jobs")
            
            all_candidates = []
            for job in jobs:
                candidates = self.get_candidates_by_job_id(job["id"], headers)
                logger.info(
                    f"Job '{job['title']}': Found {len(candidates)} candidates"
                )
                all_candidates.extend(candidates)
            
            # Process in batches
            return self.batch_download_resumes(all_candidates)
            
        finally:
            self.cleanup_temp_dir()

    def get_candidates_by_job_id(self, job_id: str, headers: Dict) -> List[Dict]:
        """Fetch all associated candidates for a job (paginated)."""
        candidates = []
        page = 1
        per_page = 200  # Zoho's max page size
        
        while True:
            url = f"{self.base_url}/Job_Openings/{job_id}/associate?page={page}&per_page={per_page}"
            
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json().get("data", [])
                
                if not data:
                    break
                    
                candidates.extend([
                    {"id": c["id"], "Full_Name": c.get("Full_Name", "Unknown")}
                    for c in data if c.get("Candidate_Status") == "Associated"
                ])
                
                logger.debug(f"Page {page}: Found {len(data)} candidates")
                
                if len(data) < per_page:
                    break
                    
                page += 1
                
            except Exception as e:
                logger.error(f"Failed to fetch candidates: {str(e)}")
                break
                
        logger.info(f"Total candidates for job {job_id}: {len(candidates)}")
        return candidates