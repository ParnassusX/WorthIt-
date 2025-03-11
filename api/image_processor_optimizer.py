"""Image Processing Optimizer for WorthIt!

This module provides advanced optimization strategies for the image processing pipeline including:
- Parallel processing for batch operations
- Adaptive quality settings based on image content
- Format conversion optimization (WebP support)
- Progressive loading support
- Caching strategies for processed images
"""

import asyncio
import logging
import time
import io
import hashlib
from typing import Dict, List, Any, Optional, Tuple, BinaryIO
from PIL import Image, ImageOps
import numpy as np
from fastapi import UploadFile

from api.data_cache import DataCache
from api.image_processor import ImageProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageProcessingOptimizer:
    """Optimizes the image processing pipeline for improved performance."""
    
    def __init__(self, image_processor: ImageProcessor = None, data_cache: DataCache = None):
        """Initialize the image processing optimizer.
        
        Args:
            image_processor: An instance of the base ImageProcessor
            data_cache: An optional instance of DataCache for caching processed images
        """
        self.image_processor = image_processor or ImageProcessor()
        self.data_cache = data_cache
        self.max_workers = 16  # Increased parallel processing capacity for production
        self.semaphore = asyncio.Semaphore(self.max_workers)
        
        # Enable advanced optimization features for production
        self.enable_webp_conversion = True
        self.enable_adaptive_quality = True
        self.enable_progressive_loading = True
        self.enable_content_aware_compression = True
        
        # Performance metrics
        self.metrics = {
            'total_processed': 0,
            'cache_hits': 0,
            'processing_time_ms': [],
            'bytes_saved': 0,
            'parallel_batches': 0,
            'optimization_level_used': []
        }
        
        # Optimization settings
        self.optimization_settings = {
            'use_webp': True,              # Use WebP format when supported
            'adaptive_quality': True,      # Dynamically adjust quality based on content
            'progressive_jpeg': True,      # Use progressive JPEG for better perceived loading
            'parallel_processing': True,   # Process images in parallel when possible
            'smart_resizing': True,        # Use content-aware resizing when appropriate
            'lazy_processing': True        # Process images on-demand
        }
        
        # Format-specific quality settings
        self.quality_settings = {
            'jpeg': {'min': 70, 'max': 95, 'default': 85},
            'webp': {'min': 75, 'max': 90, 'default': 80},
            'png': {'compression': 6}  # 0-9 scale
        }
        
    async def optimize_image(self, image_data: bytes, format: str = None, 
                          width: int = None, height: int = None) -> bytes:
        """Optimize an image with the best settings for quality and performance.
        
        Args:
            image_data: Raw image data
            format: Optional target format (jpeg, png, webp)
            width: Optional target width
            height: Optional target height
            
        Returns:
            Optimized image data
        """
        start_time = time.time()
        original_size = len(image_data)
        
        # Generate cache key if caching is available
        cache_key = None
        if self.data_cache:
            cache_params = f"{hashlib.md5(image_data).hexdigest()}-{format or 'orig'}-{width or 0}-{height or 0}"
            cache_key = f"img_opt_{cache_params}"
            
            # Try to get from cache
            cached_result = await self.data_cache.get_data('image', cache_key)
            if cached_result:
                self.metrics['cache_hits'] += 1
                self.metrics['total_processed'] += 1
                return cached_result
        
        try:
            # Use semaphore to limit concurrent processing
            async with self.semaphore:
                # Determine best format based on browser support and image content
                target_format = self._determine_best_format(format)
                
                # Open image
                img = Image.open(io.BytesIO(image_data))
                
                # Resize if needed
                if width or height:
                    img = self._smart_resize(img, width, height)
                
                # Determine optimal quality setting based on image content
                quality = self._determine_optimal_quality(img, target_format)
                
                # Apply format-specific optimizations
                optimized_img = self._apply_format_optimizations(img, target_format, quality)
                
                # Convert to bytes
                output_buffer = io.BytesIO()
                if target_format == 'webp':
                    optimized_img.save(output_buffer, 'WEBP', quality=quality)
                elif target_format == 'jpeg':
                    optimized_img.save(output_buffer, 'JPEG', quality=quality, 
                                     progressive=self.optimization_settings['progressive_jpeg'])
                elif target_format == 'png':
                    optimized_img.save(output_buffer, 'PNG', 
                                     compress_level=self.quality_settings['png']['compression'])
                else:
                    # Default fallback
                    optimized_img.save(output_buffer, format or img.format)
                
                output_buffer.seek(0)
                result = output_buffer.getvalue()
                
                # Update metrics
                self.metrics['total_processed'] += 1
                self.metrics['processing_time_ms'].append((time.time() - start_time) * 1000)
                self.metrics['bytes_saved'] += max(0, original_size - len(result))
                
                # Cache the result if caching is available
                if self.data_cache and cache_key:
                    await self.data_cache.set_data('image', cache_key, result, expire=86400)  # 24 hour cache
                
                return result
                
        except Exception as e:
            logger.error(f"Error optimizing image: {str(e)}")
            # Return original image data as fallback
            return image_data
    
    async def batch_optimize(self, images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Optimize multiple images in parallel.
        
        Args:
            images: List of dictionaries with 'data' and optional 'format', 'width', 'height' keys
            
        Returns:
            List of dictionaries with optimized image data
        """
        if not self.optimization_settings['parallel_processing'] or len(images) <= 1:
            # Process sequentially if parallel processing is disabled or only one image
            results = []
            for img in images:
                optimized = await self.optimize_image(
                    img['data'], 
                    img.get('format'), 
                    img.get('width'), 
                    img.get('height')
                )
                results.append({
                    'data': optimized,
                    'original_size': len(img['data']),
                    'optimized_size': len(optimized)
                })
            return results
        
        # Process in parallel
        self.metrics['parallel_batches'] += 1
        tasks = []
        for img in images:
            task = asyncio.create_task(self.optimize_image(
                img['data'], 
                img.get('format'), 
                img.get('width'), 
                img.get('height')
            ))
            tasks.append(task)
        
        # Wait for all tasks to complete
        optimized_data = await asyncio.gather(*tasks)
        
        # Prepare results
        results = []
        for i, data in enumerate(optimized_data):
            results.append({
                'data': data,
                'original_size': len(images[i]['data']),
                'optimized_size': len(data)
            })
        
        return results
    
    def _determine_best_format(self, requested_format: Optional[str]) -> str:
        """Determine the best format based on the requested format and optimization settings.
        
        Args:
            requested_format: The requested output format
            
        Returns:
            The best format to use
        """
        if requested_format:
            return requested_format.lower()
            
        # If WebP is enabled, prefer it for better compression
        if self.optimization_settings['use_webp']:
            return 'webp'
            
        # Default to JPEG for most images
        return 'jpeg'
    
    def _smart_resize(self, img: Image.Image, width: Optional[int], height: Optional[int]) -> Image.Image:
        """Resize an image using smart resizing techniques.
        
        Args:
            img: PIL Image object
            width: Target width
            height: Target height
            
        Returns:
            Resized PIL Image
        """
        if not width and not height:
            return img
            
        original_width, original_height = img.size
        
        # Calculate new dimensions while maintaining aspect ratio
        if width and height:
            # Both dimensions specified - use thumbnail to maintain aspect ratio within bounds
            img.thumbnail((width, height), Image.LANCZOS)
            return img
        elif width:
            # Only width specified
            ratio = width / original_width
            new_height = int(original_height * ratio)
            return img.resize((width, new_height), Image.LANCZOS)
        else:
            # Only height specified
            ratio = height / original_height
            new_width = int(original_width * ratio)
            return img.resize((new_width, height), Image.LANCZOS)
    
    def _determine_optimal_quality(self, img: Image.Image, format: str) -> int:
        """Determine the optimal quality setting based on image content.
        
        Args:
            img: PIL Image object
            format: Target format
            
        Returns:
            Quality setting (0-100 for JPEG/WebP)
        """
        if not self.optimization_settings['adaptive_quality']:
            # Use default quality if adaptive quality is disabled
            return self.quality_settings.get(format, {}).get('default', 85)
        
        try:
            # Convert to numpy array for analysis
            img_array = np.array(img)
            
            # Calculate image complexity (standard deviation of pixel values)
            complexity = np.std(img_array)
            
            if format in ('jpeg', 'webp'):
                # Scale complexity to quality range
                min_quality = self.quality_settings[format]['min']
                max_quality = self.quality_settings[format]['max']
                
                # Higher complexity = higher quality needed
                if complexity > 80:  # High complexity image
                    return max_quality
                elif complexity < 20:  # Low complexity image
                    return min_quality
                else:
                    # Linear interpolation between min and max quality
                    quality_range = max_quality - min_quality
                    quality = min_quality + (complexity / 80) * quality_range
                    return int(quality)
            
            # For PNG, return the default compression level
            return self.quality_settings['png']['compression']
            
        except Exception as e:
            logger.warning(f"Error determining optimal quality: {str(e)}")
            # Fallback to default quality
            return self.quality_settings.get(format, {}).get('default', 85)
    
    def _apply_format_optimizations(self, img: Image.Image, format: str, quality: int) -> Image.Image:
        """Apply format-specific optimizations to the image.
        
        Args:
            img: PIL Image object
            format: Target format
            quality: Quality setting
            
        Returns:
            Optimized PIL Image
        """
        if format == 'jpeg':
            # Convert to RGB mode if needed (JPEG doesn't support alpha channel)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                return background
            elif img.mode != 'RGB':
                return img.convert('RGB')
        
        elif format == 'webp':
            # WebP supports transparency, but convert palette mode
            if img.mode == 'P':
                return img.convert('RGBA')
        
        # Return original image if no specific optimizations needed
        return img
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for the image processing optimizer.
        
        Returns:
            Dictionary with performance metrics
        """
        metrics = self.metrics.copy()
        
        # Calculate averages
        if metrics['processing_time_ms']:
            metrics['avg_processing_time_ms'] = sum(metrics['processing_time_ms']) / len(metrics['processing_time_ms'])
        else:
            metrics['avg_processing_time_ms'] = 0
            
        # Calculate compression ratio
        if metrics['total_processed'] > 0:
            metrics['avg_bytes_saved_per_image'] = metrics['bytes_saved'] / metrics['total_processed']
        else:
            metrics['avg_bytes_saved_per_image'] = 0
            
        # Calculate cache hit ratio
        if metrics['total_processed'] > 0:
            metrics['cache_hit_ratio'] = metrics['cache_hits'] / metrics['total_processed']
        else:
            metrics['cache_hit_ratio'] = 0
            
        # Remove raw processing time list to keep the metrics concise
        metrics.pop('processing_time_ms')
        
        return metrics

# Singleton instance for application-wide use
_optimizer_instance = None

def get_image_processing_optimizer() -> ImageProcessingOptimizer:
    """Get the singleton instance of ImageProcessingOptimizer.
    
    Returns:
        The ImageProcessingOptimizer instance
    """
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = ImageProcessingOptimizer()
    return _optimizer_instance