"""
Configuration management for GCGAAP.

Handles global configuration settings such as numeric tolerance for
validation and accounting equation checks.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GCGAAPConfig:
    """
    Global configuration for GCGAAP validation and reporting.
    
    Attributes:
        numeric_tolerance: Maximum absolute difference for considering
                          numeric values equal in accounting checks.
                          Default: 0.01 (one cent in most currencies).
        default_currency: The primary currency symbol for reporting.
                         Default: "USD".
    """
    
    numeric_tolerance: float = 0.01
    default_currency: str = "USD"
    
    def is_zero(self, value: float) -> bool:
        """
        Check if a numeric value is effectively zero within tolerance.
        
        Args:
            value: The numeric value to check.
            
        Returns:
            True if abs(value) <= numeric_tolerance, False otherwise.
        """
        return abs(value) <= self.numeric_tolerance
    
    def is_balanced(self, value: float) -> bool:
        """
        Check if a value represents a balanced state (effectively zero).
        
        This is an alias for is_zero() but with clearer semantic meaning
        when checking accounting equation balance.
        
        Args:
            value: The balance delta to check.
            
        Returns:
            True if the value is within tolerance of zero.
        """
        return self.is_zero(value)


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the application.
    
    Args:
        verbose: If True, sets log level to DEBUG. Otherwise, INFO.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    if verbose:
        logger.debug("Verbose logging enabled")


# Global default configuration instance
default_config = GCGAAPConfig()
