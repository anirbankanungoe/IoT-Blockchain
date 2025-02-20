import os
import pandas as pd
from datetime import datetime
import psutil
import time
import threading
from pathlib import Path

class BlockchainMetricsManager:
    def __init__(self, base_path="/app/metrics"):
        """Initialize the metrics manager"""
        self.base_path = Path(base_path)
        self._create_directory_structure()
        
        # Create locks for file access
        self.file_locks = {
            'delay': threading.Lock(),
            'memory': threading.Lock(),
            'cpu': threading.Lock()
        }
        
        # Start periodic cleanup
        self.start_cleanup_thread()

    def _create_directory_structure(self):
        """Create the directory structure for metrics storage"""
        directories = [
            'delay/summaries',
            'memory/summaries',
            'cpu/summaries',
            'comparisons'
        ]
        
        for dir_path in directories:
            full_path = self