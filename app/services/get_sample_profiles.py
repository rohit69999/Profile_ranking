import requests
import os
import logging
from .zoho_auth import get_access_token
import tempfile
import streamlit as st 
class ZohoSampleProfileService:
    def __init__(self):
        # self.base_url = os.getenv("ZOHO_RECRUIT_BASE_API_URL")
        self.base_url = st.secrets["ZOHO_RECRUIT_BASE_API_URL"]
        # Create a temporary directory with a specific prefix that won't be cleaned up automatically
        self.output_dir = tempfile.mkdtemp(prefix="sample_resumes_")
        # Ensure the directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        # Register cleanup on program exit
        import atexit
        atexit.register(self.cleanup)
        
    def cleanup(self):
        """Clean up the temporary directory"""
        if hasattr(self, 'output_dir') and os.path.exists(self.output_dir):
            try:
                import shutil
                shutil.rmtree(self.output_dir)
                logging.info(f"Cleaned up sample profiles directory: {self.output_dir}")
            except Exception as e:
                logging.error(f"Error cleaning up sample profiles directory: {str(e)}")

    def download_sample_profiles_by_job_id(self, job_id: str, output_dir: str = None) -> str:
        """
        Download sample resumes for a job and return the directory path where files were downloaded.
        
        Args:
            job_id: The job ID to download sample profiles for
            output_dir: Optional directory to save files. If not provided, creates a new temp directory.
            
        Returns:
            str: Path to the directory containing downloaded files, or empty string on failure
        """
        try:
            access_token = get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
            
            attachments = self.get_sample_profile_attachments(job_id, headers)
            if not attachments:
                logging.warning(f"No attachments found for job {job_id}")
                return ""

            # Use provided output_dir or create a new temp directory
            if output_dir:
                save_dir = output_dir
                os.makedirs(save_dir, exist_ok=True)
            else:
                # Create a new temp directory for this specific download
                save_dir = tempfile.mkdtemp(prefix=f"sample_resumes_{job_id}_")
                logging.info(f"Created temporary directory for sample resumes: {save_dir}")

            downloaded_count = 0
            for att in attachments:
                att_id = att.get("id")
                file_name = att.get("File_Name")
                
                if not all([att_id, file_name]):
                    logging.warning(f"Skipping invalid attachment data: {att}")
                    continue
                    
                if self.download_attachment(job_id, att_id, file_name, headers, save_dir):
                    downloaded_count += 1
            
            if downloaded_count == 0:
                logging.error("No files were successfully downloaded")
                if save_dir != output_dir:  # Only clean up if we created this directory
                    try:
                        os.rmdir(save_dir)  # Remove empty directory
                    except OSError:
                        pass
                return ""
                    
            logging.info(f"Successfully downloaded {downloaded_count} sample resumes to {save_dir}")
            return save_dir
            
        except Exception as e:
            logging.error(f"Error downloading sample profiles: {str(e)}", exc_info=True)
            return ""

    def get_sample_profile_attachments(self, job_id, headers):
        """
        Get sample profile attachments for a job opening with improved error handling
        and response validation.
        """
        url = f"{self.base_url}/Job_Openings/{job_id}/Attachments"
        
        try:
            response = requests.get(url, headers=headers)
            
            # Log the response status and content for debugging
            logging.debug(f"Response status code: {response.status_code}")
            logging.debug(f"Response content: {response.text[:200]}...")  # First 200 chars
            
            # Check for specific status codes
            if response.status_code == 204:
                logging.info(f"No attachments found for job {job_id}")
                return []
                
            if response.status_code == 429:
                logging.error("Rate limit exceeded")
                raise requests.RequestException("Rate limit exceeded")
                
            if response.status_code != 200:
                logging.error(f"API request failed with status {response.status_code}")
                return []
            
            # Validate response content
            if not response.text:
                logging.warning(f"Empty response received for job {job_id}")
                return []
                
            try:
                data = response.json()
            except ValueError as e:
                logging.error(f"Invalid JSON response for job {job_id}: {str(e)}")
                return []
                
            # Check for error messages in response
            if "error" in data:
                error_msg = data.get("error", {}).get("message", "Unknown error")
                logging.error(f"API error for job {job_id}: {error_msg}")
                return []
                
            # Extract attachments with proper validation
            attachments = data.get("data", [])
            if not isinstance(attachments, list):
                logging.error(f"Unexpected data format for job {job_id}")
                return []
                
            # Filter sample profiles
            sample_profiles = [
                att for att in attachments
                if isinstance(att, dict) and 
                att.get("Category", {}).get("name") == "Sample candidate Profiles"
            ]
            
            logging.info(f"Found {len(sample_profiles)} sample profiles for job {job_id}")
            return sample_profiles
            
        except requests.RequestException as e:
            logging.error(f"Network error fetching attachments for job {job_id}: {str(e)}")
            return []
        except Exception as e:
            logging.error(f"Unexpected error for job {job_id}: {str(e)}")
            return []

    def download_attachment(self, job_id, attachment_id, file_name, headers, save_dir):
        """
        Download an attachment from Zoho Recruit.
        
        Args:
            job_id: The job ID
            attachment_id: The attachment ID
            file_name: Original file name
            headers: Request headers with auth
            save_dir: Directory to save the file
            
        Returns:
            bool: True if download was successful, False otherwise
        """
        if not all([job_id, attachment_id, file_name, save_dir]):
            logging.error("Missing required parameters for download_attachment")
            return False
            
        url = f"{self.base_url}/Job_Openings/{job_id}/Attachments/{attachment_id}"
        
        try:
            # Validate save directory
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
                
            if not os.path.isdir(save_dir):
                logging.error(f"Save path is not a directory: {save_dir}")
                return False
                
            # Sanitize filename
            base_name = os.path.basename(file_name)
            safe_name = "".join(
                c if c.isalnum() or c in ' .-_‌' else '_' 
                for c in base_name
            ).strip()
            
            # Ensure we have a valid file extension
            name, ext = os.path.splitext(safe_name)
            if not ext or ext.lower() not in ['.pdf', '.docx', '.doc']:
                ext = '.pdf'  # Default to PDF if no valid extension
                safe_name = f"{name}{ext}"
                
            file_path = os.path.join(save_dir, safe_name)
            
            # Make sure we don't overwrite existing files
            counter = 1
            base_path, ext = os.path.splitext(file_path)
            while os.path.exists(file_path):
                file_path = f"{base_path}_{counter}{ext}"
                counter += 1
            
            logging.info(f"Downloading attachment {attachment_id} to {file_path}")
            
            # Stream the download to handle large files
            with requests.get(url, headers=headers, stream=True, timeout=30) as response:
                response.raise_for_status()
                
                # Check content type to validate it's a valid file
                content_type = response.headers.get('content-type', '').lower()
                if 'application/json' in content_type:
                    # This is likely an error message, not a file
                    error_data = response.json()
                    logging.error(f"API error downloading {file_name}: {error_data}")
                    return False
                    
                # Save the file
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
            
            # Verify the file was saved and has content
            if not os.path.exists(file_path):
                logging.error(f"Download failed: File not saved to {file_path}")
                return False
                
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logging.error(f"Download failed: Empty file saved to {file_path}")
                os.remove(file_path)  # Clean up empty file
                return False
                
            logging.info(f"Successfully downloaded {file_name} ({file_size} bytes) to {file_path}")
            return True
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error downloading {file_name}: {str(e)}")
            return False
        except IOError as e:
            logging.error(f"File system error saving {file_name}: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error downloading {file_name}: {str(e)}", exc_info=True)
            return False
