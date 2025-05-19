import os
import shutil
import tempfile
import logging
from typing import Optional

class CleanupService:
    """Service to handle cleanup of temporary files and directories"""
    
    @staticmethod
    def cleanup_temp_files() -> None:
        """Clean up all temporary files and Python cache directories."""
        try:
            # Get the root directory of the project
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            # Clean up __pycache__ directories
            CleanupService._cleanup_cache_dirs(root_dir)
            
            # Clean up temp directories
            CleanupService._cleanup_temp_dirs()
            
        except Exception as e:
            logging.error(f"Error during cleanup: {str(e)}")

    @staticmethod
    def cleanup_upload_dirs(temp_dir: Optional[str] = None, good_dir: Optional[str] = None) -> None:
        """Clean up upload directories"""
        try:
            # Clean up resume directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logging.info(f"Cleaned up temp directory: {temp_dir}")
            
            # Clean up good resumes directory
            if good_dir and os.path.exists(good_dir):
                shutil.rmtree(good_dir)
                logging.info(f"Cleaned up good resumes directory: {good_dir}")
                
        except Exception as e:
            logging.error(f"Error cleaning up upload directories: {str(e)}")

    @staticmethod
    def cleanup_job_desc_files(temp_path: Optional[str] = None, temp_dir: Optional[str] = None) -> None:
        """Clean up job description temporary files"""
        try:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
                logging.info(f"Removed temporary file: {temp_path}")
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logging.info(f"Removed temporary directory: {temp_dir}")
        except Exception as e:
            logging.error(f"Error cleaning up job description files: {str(e)}")

    @staticmethod
    def _cleanup_cache_dirs(root_dir: str) -> None:
        """Clean up Python cache directories"""
        try:
            for root, dirs, files in os.walk(root_dir):
                for dir_name in dirs:
                    if dir_name == '__pycache__' or dir_name.endswith('.pyc'):
                        cache_dir = os.path.join(root, dir_name)
                        try:
                            shutil.rmtree(cache_dir)
                            logging.info(f"Removed cache directory: {cache_dir}")
                        except Exception as e:
                            logging.error(f"Error removing cache directory {cache_dir}: {str(e)}")
        except Exception as e:
            logging.error(f"Error cleaning up cache directories: {str(e)}")

    @staticmethod
    def _cleanup_temp_dirs() -> None:
        """Clean up temporary directories"""
        try:
            temp_dir = tempfile.gettempdir()
            for item in os.listdir(temp_dir):
                if item.startswith('tmp'):
                    item_path = os.path.join(temp_dir, item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.unlink(item_path)
                        logging.info(f"Removed temporary item: {item_path}")
                    except Exception as e:
                        logging.error(f"Error removing temporary item {item_path}: {str(e)}")
        except Exception as e:
            logging.error(f"Error cleaning up temp directories: {str(e)}") 