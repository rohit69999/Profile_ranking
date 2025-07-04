"""Custom exceptions for the Zoho integration."""

class ZohoAPIError(Exception):
    """Base exception for Zoho API errors."""
    pass

class ZohoTokenError(ZohoAPIError):
    """Raised when there's an error with the Zoho authentication token."""
    pass

class ZohoRateLimitError(ZohoAPIError):
    """Raised when the Zoho API rate limit is exceeded."""
    pass

class ZohoNoDataError(ZohoAPIError):
    """Raised when no data is returned from the Zoho API."""
    pass
