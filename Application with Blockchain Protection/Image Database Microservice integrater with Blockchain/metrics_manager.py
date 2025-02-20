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
        
        # Initialize DataFrames
        self._initialize_dataframes()
        
        # Start periodic cleanup and summary generation
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
            full_path = self.base_path / dir_path
            full_path.mkdir(parents=True, exist_ok=True)

    def _initialize_dataframes(self):
        """Initialize Excel files with headers if they don't exist"""
        files_and_headers = {
            'delay/raw_data.xlsx': [
                'timestamp', 'source_service', 'destination_service',
                'packet_id', 'packet_size', 'delay_ms', 'blockchain_enabled'
            ],
            'memory/raw_data.xlsx': [
                'timestamp', 'service_name', 'memory_usage_mb',
                'blockchain_enabled', 'total_memory_mb', 'memory_percent'
            ],
            'cpu/raw_data.xlsx': [
                'timestamp', 'service_name', 'cpu_percent',
                'blockchain_enabled', 'core_count', 'cpu_freq_mhz'
            ]
        }
        
        for file_path, headers in files_and_headers.items():
            full_path = self.base_path / file_path
            if not full_path.exists():
                df = pd.DataFrame(columns=headers)
                df.to_excel(full_path, index=False)

    def record_delay(self, source_service, destination_service, packet_id, 
                    packet_size, delay_ms, blockchain_enabled):
        """Record packet delay metrics"""
        with self.file_locks['delay']:
            try:
                file_path = self.base_path / 'delay/raw_data.xlsx'
                df = pd.read_excel(file_path)
                
                new_row = {
                    'timestamp': datetime.now().isoformat(),
                    'source_service': source_service,
                    'destination_service': destination_service,
                    'packet_id': packet_id,
                    'packet_size': packet_size,
                    'delay_ms': delay_ms,
                    'blockchain_enabled': blockchain_enabled
                }
                
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_excel(file_path, index=False)
                
            except Exception as e:
                print(f"Error recording delay metrics: {str(e)}")

    def record_memory_usage(self, service_name, blockchain_enabled):
        """Record memory usage metrics"""
        with self.file_locks['memory']:
            try:
                file_path = self.base_path / 'memory/raw_data.xlsx'
                df = pd.read_excel(file_path)
                
                process = psutil.Process()
                memory_info = process.memory_info()
                
                new_row = {
                    'timestamp': datetime.now().isoformat(),
                    'service_name': service_name,
                    'memory_usage_mb': memory_info.rss / 1024 / 1024,
                    'blockchain_enabled': blockchain_enabled,
                    'total_memory_mb': psutil.virtual_memory().total / 1024 / 1024,
                    'memory_percent': process.memory_percent()
                }
                
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_excel(file_path, index=False)
                
            except Exception as e:
                print(f"Error recording memory metrics: {str(e)}")

    def record_cpu_usage(self, service_name, blockchain_enabled):
        """Record CPU usage metrics"""
        with self.file_locks['cpu']:
            try:
                file_path = self.base_path / 'cpu/raw_data.xlsx'
                df = pd.read_excel(file_path)
                
                process = psutil.Process()
                
                new_row = {
                    'timestamp': datetime.now().isoformat(),
                    'service_name': service_name,
                    'cpu_percent': process.cpu_percent(),
                    'blockchain_enabled': blockchain_enabled,
                    'core_count': psutil.cpu_count(),
                    'cpu_freq_mhz': psutil.cpu_freq().current if psutil.cpu_freq() else 0
                }
                
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_excel(file_path, index=False)
                
            except Exception as e:
                print(f"Error recording CPU metrics: {str(e)}")

    def generate_summaries(self):
        """Generate summary reports for all metrics"""
        try:
            # Generate delay summaries
            self._generate_delay_summaries()
            
            # Generate memory summaries
            self._generate_memory_summaries()
            
            # Generate CPU summaries
            self._generate_cpu_summaries()
            
            # Generate comparison reports
            self._generate_comparison_reports()
            
        except Exception as e:
            print(f"Error generating summaries: {str(e)}")

    def _generate_delay_summaries(self):
        """Generate delay metric summaries"""
        try:
            delay_df = pd.read_excel(self.base_path / 'delay/raw_data.xlsx')
            delay_df['timestamp'] = pd.to_datetime(delay_df['timestamp'])
            
            # Daily summary
            daily_delay = delay_df.groupby([
                delay_df['timestamp'].dt.date,
                'blockchain_enabled',
                'source_service',
                'destination_service'
            ]).agg({
                'delay_ms': ['mean', 'min', 'max', 'std'],
                'packet_size': ['mean', 'sum']
            }).reset_index()
            
            daily_delay.to_excel(
                self.base_path / 'delay/summaries/daily_summary.xlsx'
            )
            
        except Exception as e:
            print(f"Error generating delay summaries: {str(e)}")

    def _generate_memory_summaries(self):
        """Generate memory usage summaries"""
        try:
            memory_df = pd.read_excel(self.base_path / 'memory/raw_data.xlsx')
            memory_df['timestamp'] = pd.to_datetime(memory_df['timestamp'])
            
            # Service summary
            service_memory = memory_df.groupby([
                'service_name',
                'blockchain_enabled'
            ]).agg({
                'memory_usage_mb': ['mean', 'max'],
                'memory_percent': 'mean'
            }).reset_index()
            
            service_memory.to_excel(
                self.base_path / 'memory/summaries/service_summary.xlsx'
            )
            
        except Exception as e:
            print(f"Error generating memory summaries: {str(e)}")

    def _generate_cpu_summaries(self):
        """Generate CPU usage summaries"""
        try:
            cpu_df = pd.read_excel(self.base_path / 'cpu/raw_data.xlsx')
            cpu_df['timestamp'] = pd.to_datetime(cpu_df['timestamp'])
            
            # Service summary
            service_cpu = cpu_df.groupby([
                'service_name',
                'blockchain_enabled'
            ]).agg({
                'cpu_percent': ['mean', 'max']
            }).reset_index()
            
            service_cpu.to_excel(
                self.base_path / 'cpu/summaries/service_summary.xlsx'
            )
            
        except Exception as e:
            print(f"Error generating CPU summaries: {str(e)}")

    def _generate_comparison_reports(self):
        """Generate blockchain vs non-blockchain comparison reports"""
        try:
            # Delay comparison
            delay_df = pd.read_excel(self.base_path / 'delay/raw_data.xlsx')
            delay_comparison = delay_df.groupby('blockchain_enabled').agg({
                'delay_ms': ['mean', 'min', 'max', 'std'],
                'packet_size': ['mean', 'sum']
            }).reset_index()
            
            delay_comparison.to_excel(
                self.base_path / 'comparisons/blockchain_vs_normal_delay.xlsx'
            )
            
            # Memory comparison
            memory_df = pd.read_excel(self.base_path / 'memory/raw_data.xlsx')
            memory_comparison = memory_df.groupby('blockchain_enabled').agg({
                'memory_usage_mb': ['mean', 'max'],
                'memory_percent': 'mean'
            }).reset_index()
            
            memory_comparison.to_excel(
                self.base_path / 'comparisons/blockchain_vs_normal_memory.xlsx'
            )
            
            # CPU comparison
            cpu_df = pd.read_excel(self.base_path / 'cpu/raw_data.xlsx')
            cpu_comparison = cpu_df.groupby('blockchain_enabled').agg({
                'cpu_percent': ['mean', 'max']
            }).reset_index()
            
            cpu_comparison.to_excel(
                self.base_path / 'comparisons/blockchain_vs_normal_cpu.xlsx'
            )
            
        except Exception as e:
            print(f"Error generating comparison reports: {str(e)}")

    def start_cleanup_thread(self):
        """Start a background thread for periodic cleanup and summary generation"""
        def cleanup_task():
            while True:
                try:
                    self.generate_summaries()
                    time.sleep(300)  # Generate summaries every 5 minutes
                except Exception as e:
                    print(f"Error in cleanup task: {str(e)}")
                    time.sleep(60)

        cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
        cleanup_thread.start()