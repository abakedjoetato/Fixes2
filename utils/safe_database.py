"""
Safe Database Access Utilities

This module provides utilities for safely accessing MongoDB data with proper
error handling, type checking, and consistent patterns.
"""

import logging
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic, cast

logger = logging.getLogger(__name__)

# Type variables for generic function annotations
T = TypeVar('T')
D = TypeVar('D', bound=Dict[str, Any])

def safe_get(data: Optional[Dict[str, Any]], key: str, default: T = None) -> Optional[T]:
    """
    Safely get a value from a dictionary with proper error handling
    
    Args:
        data: Dictionary to retrieve value from
        key: Dictionary key to access
        default: Default value to return if key doesn't exist
        
    Returns:
        Value from the dictionary or default if key doesn't exist or dict is None
    """
    if data is None:
        return default
    
    try:
        return data.get(key, default)
    except (AttributeError, KeyError):
        logger.debug(f"Failed to access key '{key}' in dictionary")
        return default

def safe_get_nested(data: Optional[Dict[str, Any]], path: str, default: Any = None, 
                    delimiter: str = '.') -> Any:
    """
    Safely get a nested value from a dictionary using a dot-notation path
    
    Args:
        data: Dictionary to retrieve value from
        path: Dot-notation path to the value (e.g., 'user.profile.name')
        default: Default value to return if path doesn't exist
        delimiter: Delimiter to use for path segments (default: '.')
        
    Returns:
        Value from the nested path or default if path doesn't exist
    """
    if data is None:
        return default
    
    keys = path.split(delimiter)
    result = data
    
    try:
        for key in keys:
            if not isinstance(result, dict):
                return default
            
            result = result.get(key)
            if result is None:
                return default
        
        return result
    except (AttributeError, KeyError):
        logger.debug(f"Failed to access nested path '{path}' in dictionary")
        return default

def is_db_available(db):
    """
    Check if database connection is available and ready to use
    
    Args:
        db: MongoDB database instance
        
    Returns:
        bool: True if database is available, False otherwise
    """
    if db is None:
        return False
    
    try:
        # Lightweight check that doesn't require a server round-trip
        return hasattr(db, 'client') and hasattr(db, 'name')
    except (AttributeError, Exception) as e:
        logger.error(f"Database availability check failed: {e}")
        return False

async def get_document_safely(collection, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Safely retrieve a document from a MongoDB collection with error handling
    
    Args:
        collection: MongoDB collection to query
        query: Query dictionary to find the document
        
    Returns:
        Document dict or None if not found or error occurs
    """
    if collection is None:
        return None
    
    try:
        return await collection.find_one(query)
    except Exception as e:
        logger.error(f"Error retrieving document: {e}")
        return None

def document_exists(document: Optional[Dict[str, Any]]) -> bool:
    """
    Safely check if a document exists and is not empty
    
    Args:
        document: Document to check
        
    Returns:
        bool: True if document exists and is not empty, False otherwise
    """
    return document is not None and len(document) > 0

async def safely_update_document(collection, query: Dict[str, Any], 
                                update: Dict[str, Any], upsert: bool = False) -> bool:
    """
    Safely update a document in a MongoDB collection with error handling
    
    Args:
        collection: MongoDB collection to update
        query: Query to find the document to update
        update: Update operation to apply
        upsert: Whether to insert if document doesn't exist
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    if collection is None:
        return False
    
    try:
        result = await collection.update_one(query, update, upsert=upsert)
        # Check if acknowledged and at least one document was modified
        return result.acknowledged and (result.modified_count > 0 or 
                                        (upsert and result.upserted_id is not None))
    except Exception as e:
        logger.error(f"Error updating document: {e}")
        return False

async def count_documents_safely(collection, query: Dict[str, Any]) -> int:
    """
    Safely count documents in a MongoDB collection with error handling
    
    Args:
        collection: MongoDB collection to query
        query: Query to count matching documents
        
    Returns:
        int: Count of matching documents or 0 if error occurs
    """
    if collection is None:
        return 0
    
    try:
        return await collection.count_documents(query)
    except Exception as e:
        logger.error(f"Error counting documents: {e}")
        return 0

async def find_documents_safely(collection, query: Dict[str, Any], 
                              limit: int = 0, sort=None) -> List[Dict[str, Any]]:
    """
    Safely find documents in a MongoDB collection with error handling
    
    Args:
        collection: MongoDB collection to query
        query: Query to find matching documents
        limit: Maximum number of documents to return (0 for no limit)
        sort: Sort specification
        
    Returns:
        List of matching documents or empty list if error occurs
    """
    if collection is None:
        return []
    
    try:
        cursor = collection.find(query)
        
        if sort is not None:
            cursor = cursor.sort(sort)
        
        if limit > 0:
            cursor = cursor.limit(limit)
        
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error(f"Error finding documents: {e}")
        return []

def get_field_with_type_check(data: Optional[Dict[str, Any]], key: str, 
                            expected_type: type, default: T) -> T:
    """
    Get a field from a dictionary with type checking
    
    Args:
        data: Dictionary to retrieve value from
        key: Dictionary key to access
        expected_type: Expected type of the value
        default: Default value to return if key doesn't exist or type doesn't match
        
    Returns:
        Value from the dictionary if it exists and has the expected type, default otherwise
    """
    if data is None:
        return default
    
    try:
        value = data.get(key)
        
        # If value doesn't exist, return default
        if value is None:
            return default
        
        # If value is not of expected type, log warning and return default
        if not isinstance(value, expected_type):
            logger.warning(f"Field '{key}' has unexpected type: {type(value)}, expected: {expected_type}")
            return default
        
        return value
    except Exception:
        return default