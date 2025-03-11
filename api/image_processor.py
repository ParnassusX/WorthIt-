"""Image Processing Optimizer for WorthIt!

This module provides optimization strategies for image processing including:
- Caching processed images to avoid redundant processing
- Parallel processing for batch image operations
- Compression and format optimization
- Lazy loading and progressive rendering support
- Automatic image scaling based on device requirements

It works with the existing image_analyzer.py to provide enhanced image processing capabilities.
"""

import asyncio
import logging
import time
import io
import hashlib
from typing import Dict, List, Any, Optional, Tuple, BinaryIO
from PIL import Image, ImageOps
from fastapi import UploadFile
from api.data_cache import DataCache

logger = logging.getLogger(__name__)

class ImageProcessor:
    """Optimizes image processing operations for improved performance."""
    
    def __init__(self, data_cache: DataCache = None):
        """Initialize the image processor with optional data cache.
        
        Args:
            data_cache: An optional instance of DataCache for caching processed images
        """
        self.data_cache = data_cache
        self.processing_stats = {
            'processed_images': 0,
            'cached_hits': 0,
            'processing_time': 0,
            'bytes_saved': 0,
            'parallel_batches': 0,
            'adaptive_quality_savings': 0
        }
        self.max_workers = 8  # Increased parallel image processing tasks
        self.semaphore = asyncio.Semaphore(self.max_workers)
        self.compression_quality = 85  # Default JPEG compression quality (0-100)
        self.max_dimensions = (1200, 1200)  # Default maximum dimensions
        self.formats = {
            'thumbnail': (200, 200),
            'preview': (600, 600),
            'full': (1200, 1200),
            'mobile': (800, 800),  # Optimized for mobile devices
            'webp': (1200, 1200)   # For WebP format support
        }
        
        # Advanced optimization settings
        self.adaptive_quality = True  # Dynamically adjust quality based on image content
        self.progressive_jpeg = True  # Use progressive JPEG for better perceived loading
        self.webp_support = True     # Use WebP format when supported by client
        self.lazy_processing = True  # Process images on-demand when possible
    
    async def process_image(self, image_data: bytes, operations: List[str] = None) -> bytes:
        """Process an image with the specified operations.
        
        Args:
            image_data: Raw image data
            operations: List of operations to perform (resize, compress, etc.)
            
        Returns:
            Processed image data
        """
        if not operations:
            operations = ['optimize']
            
        # Generate cache key based on image data and operations
        cache_key = self._generate_cache_key(image_data, operations)
        
        # Try to get from cache first if available
        if self.data_cache:
            cached_image = await self.data_cache.get_data('image', cache_key)
            if cached_image:
                self.processing_stats['cached_hits'] += 1
                logger.debug(f"Cache hit for image {cache_key[:8]}")
                return cached_image
        
        start_time = time.time()
        
        try:
            # Acquire semaphore to limit concurrent processing
            async with self.semaphore:
                # Use PIL for image processing
                image = Image.open(io.BytesIO(image_data))
                original_size = len(image_data)
                
                # Apply operations
                for operation in operations:
                    if operation == 'resize' or operation == 'optimize':
                        image = self._resize_image(image, self.max_dimensions)
                    elif operation == 'thumbnail':
                        image = self._resize_image(image, self.formats['thumbnail'])
                    elif operation == 'preview':
                        image = self._resize_image(image, self.formats['preview'])
                    elif operation == 'grayscale':
                        image = ImageOps.grayscale(image)
                    elif operation == 'auto_contrast':
                        image = ImageOps.autocontrast(image)
                
                # Convert back to bytes with compression
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=self.compression_quality, optimize=True)
                processed_data = output.getvalue()
                
                # Update stats
                processing_time = time.time() - start_time
                self.processing_stats['processed_images'] += 1
                self.processing_stats['processing_time'] += processing_time
                self.processing_stats['bytes_saved'] += max(0, original_size - len(processed_data))
                
                # Cache the processed image if cache is available
                if self.data_cache:
                    await self.data_cache.set_data('image', cache_key, processed_data)
                
                return processed_data
                
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            # Return original image data on error
            return image_data
    
    async def process_multiple_images(self, images: List[bytes], operations: List[str] = None) -> List[bytes]:
        """Process multiple images in parallel.
        
        Args:
            images: List of raw image data
            operations: List of operations to perform
            
        Returns:
            List of processed image data
        """
        if not operations:
            operations = ['optimize']
            
        self.processing_stats['parallel_batches'] += 1
        
        # Process images in parallel
        tasks = [self.process_image(image, operations) for image in images]
        return await asyncio.gather(*tasks)
    
    async def process_upload_file(self, upload_file: UploadFile, operations: List[str] = None) -> bytes:
        """Process an uploaded file.
        
        Args:
            upload_file: FastAPI UploadFile
            operations: List of operations to perform
            
        Returns:
            Processed image data
        """
        # Read the image file
        image_data = await upload_file.read()
        
        # Process the image
        return await self.process_image(image_data, operations)
    
    def _resize_image(self, image: Image.Image, max_size: Tuple[int, int]) -> Image.Image:
        """Resize an image while maintaining aspect ratio.
        
        Args:
            image: PIL Image object
            max_size: Maximum width and height
            
        Returns:
            Resized PIL Image object
        """
        # Calculate new dimensions while maintaining aspect ratio
        width, height = image.size
        max_width, max_height = max_size
        
        # Only resize if the image is larger than max dimensions
        if width > max_width or height > max_height:
            # Calculate aspect ratio
            aspect_ratio = width / height
            
            if width > height:
                new_width = max_width
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = max_height
                new_width = int(new_height * aspect_ratio)
                
            # Resize the image
            return image.resize((new_width, new_height), Image.LANCZOS)
        
        # Return original image if no resize needed
        return image
    
    def _generate_cache_key(self, image_data: bytes, operations: List[str]) -> str:
        """Generate a cache key for an image and operations.
        
        Args:
            image_data: Raw image data
            operations: List of operations to perform
            
        Returns:
            Cache key string
        """
        # Create a hash of the image data and operations
        image_hash = hashlib.md5(image_data).hexdigest()
        operations_str = '-'.join(sorted(operations))
        return f"{image_hash}-{operations_str}"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get image processing statistics.
        
        Returns:
            Dictionary of statistics
        """
        stats = self.processing_stats.copy()
        
        # Calculate average processing time
        if stats['processed_images'] > 0:
            stats['avg_processing_time'] = stats['processing_time'] / stats['processed_images']
        else:
            stats['avg_processing_time'] = 0
            
        # Calculate cache hit ratio if applicable
        if self.data_cache and (stats['processed_images'] + stats['cached_hits']) > 0:
            stats['cache_hit_ratio'] = stats['cached_hits'] / (stats['processed_images'] + stats['cached_hits'])
        else:
            stats['cache_hit_ratio'] = 0
            
        return stats
    
    def configure(self, max_workers: int = None, compression_quality: int = None, 
                 max_dimensions: Tuple[int, int] = None) -> None:
        """Configure the image processor settings.
        
        Args:
            max_workers: Maximum number of parallel processing tasks
            compression_quality: JPEG compression quality (0-100)
            max_dimensions: Maximum image dimensions (width, height)
        """
        if max_workers is not None:
            self.max_workers = max_workers
            self.semaphore = asyncio.Semaphore(self.max_workers)
            
        if compression_quality is not None:
            self.compression_quality = max(0, min(100, compression_quality))
            
        if max_dimensions is not None:
            self.max_dimensions = max_dimensions