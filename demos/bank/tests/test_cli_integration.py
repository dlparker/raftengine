#!/usr/bin/env python
"""Integration tests for CLI tools in src/cli/"""
import pytest
import asyncio
import tempfile
import os
import subprocess
import sys
import signal
import time
import socket
from pathlib import Path
from decimal import Decimal

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cli.setup_configs import setup_configs
from cli.run_client import main_async as client_main_async
from cli.run_server import main_async as server_main_async


def get_free_port():
    """Get a free port for testing"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def check_dependency(module_name):
    """Check if a module is available"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


# Check available transports
HAS_GRPC = check_dependency('grpc')
HAS_AIOZMQ = check_dependency('aiozmq')
HAS_FASTAPI = check_dependency('fastapi')


@pytest.mark.integration
class TestCLITransports:
    """Test the CLI transport configuration"""
    
    def test_setup_configs_exists(self):
        """Test that setup configs are properly configured"""
        assert isinstance(setup_configs, dict)
        assert len(setup_configs) > 0
        
        # Check expected steps are present
        expected_steps = ['step1', 'step2']
        for step in expected_steps:
            assert step in setup_configs
            assert isinstance(setup_configs[step], dict)
        
        # Check expected transports for each step
        assert 'direct' in setup_configs['step1']
        expected_step2_transports = ['aiozmq', 'grpc', 'fastapi']
        for transport in expected_step2_transports:
            assert transport in setup_configs['step2']
    
    def test_transport_modules_importable(self):
        """Test that transport modules can be imported (where dependencies exist)"""
        # step1 should always be importable
        import importlib
        module = importlib.import_module(setup_configs['step1']['direct'])
        assert hasattr(module, 'SetupHelper')
        
        # Test step2 modules if dependencies are available
        if HAS_GRPC:
            module = importlib.import_module(setup_configs['step2']['grpc'])
            assert hasattr(module, 'SetupHelper')


@pytest.mark.integration
@pytest.mark.asyncio
class TestRunClientCLI:
    """Integration tests for run_client.py CLI tool"""
    
    def setup_method(self):
        """Set up test database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)
        self.src_dir = Path(__file__).parent.parent / "src"
        self.run_client_script = self.src_dir / "cli" / "run_client.py"
        
    def teardown_method(self):
        """Clean up test database after each test"""
        if self.db_path.exists():
            os.unlink(self.db_path)
    
    def test_run_client_help(self):
        """Test run_client.py --help"""
        result = subprocess.run([
            sys.executable, str(self.run_client_script), '--help'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode == 0
        assert 'Banking Server Client Validator' in result.stdout
        assert '--transport' in result.stdout
        assert '--database' in result.stdout
        assert '--port' in result.stdout
    
    def test_run_client_no_args(self):
        """Test run_client.py with no arguments (should fail)"""
        result = subprocess.run([
            sys.executable, str(self.run_client_script)
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode != 0
        assert 'required' in result.stderr or 'error' in result.stderr
    
    def test_run_client_invalid_transport(self):
        """Test run_client.py with invalid transport"""
        result = subprocess.run([
            sys.executable, str(self.run_client_script), 
            '-t', 'invalid_transport'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode != 0
        assert 'invalid choice' in result.stderr or 'error' in result.stderr
    
    def test_run_client_step1_success(self):
        """Test run_client.py with step1 transport (should work)"""
        result = subprocess.run([
            sys.executable, str(self.run_client_script),
            '--step', 'step1',
            '--transport', 'direct',
            '-d', str(self.db_path)
        ], capture_output=True, text=True, cwd=str(self.src_dir), timeout=10)
        
        assert result.returncode == 0
        assert 'Creating customer' in result.stdout
        assert 'Creating accounts' in result.stdout
        assert 'All banking operations completed successfully' in result.stdout
    
    async def test_run_client_step1_direct_call(self):
        """Test run_client main_async function directly for coverage"""
        # This test calls the function directly for coverage
        args = ['--step', 'step1', '--transport', 'direct', '-d', str(self.db_path)]
        await client_main_async(args)
    
    
    def test_run_client_step1_custom_database(self):
        """Test run_client.py with step1 and custom database path"""
        custom_db = self.db_path.parent / "custom_test.db"
        
        result = subprocess.run([
            sys.executable, str(self.run_client_script),
            '--step', 'step1',
            '--transport', 'direct',
            '--database', str(custom_db)
        ], capture_output=True, text=True, cwd=str(self.src_dir), timeout=10)
        
        assert result.returncode == 0
        assert custom_db.exists()  # Database should be created
        
        # Clean up
        if custom_db.exists():
            os.unlink(custom_db)
    
    def test_run_client_step2_missing_port(self):
        """Test run_client.py with step2 transport but missing port (should fail)"""
        result = subprocess.run([
            sys.executable, str(self.run_client_script),
            '--step', 'step2',
            '--transport', 'grpc',
            '-d', str(self.db_path)
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        # Should fail because port is required for step2 transports
        assert result.returncode != 0
    
    def test_run_client_list_transports(self):
        """Test that all expected transports are available in help"""
        result = subprocess.run([
            sys.executable, str(self.run_client_script), '--help'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode == 0
        # Check that step options are shown
        assert 'step1' in result.stdout
        assert 'step2' in result.stdout


@pytest.mark.integration
class TestRunServerCLI:
    """Integration tests for run_server.py CLI tool"""
    
    def setup_method(self):
        """Set up test database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)
        self.src_dir = Path(__file__).parent.parent / "src"
        self.run_server_script = self.src_dir / "cli" / "run_server.py"
        
    def teardown_method(self):
        """Clean up test database after each test"""
        if self.db_path.exists():
            os.unlink(self.db_path)
    
    def test_run_server_help(self):
        """Test run_server.py --help"""
        result = subprocess.run([
            sys.executable, str(self.run_server_script), '--help'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode == 0
        assert 'Banking Server Runner' in result.stdout
        assert '--transport' in result.stdout
        assert '--database' in result.stdout
        assert '--port' in result.stdout
        assert '--uri' in result.stdout
    
    def test_run_server_no_args(self):
        """Test run_server.py with no arguments (should fail)"""
        result = subprocess.run([
            sys.executable, str(self.run_server_script)
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode != 0
        assert 'required' in result.stderr or 'error' in result.stderr
    
    def test_run_server_step1_special_case(self):
        """Test run_server.py with step1 transport (should exit with message)"""
        result = subprocess.run([
            sys.executable, str(self.run_server_script),
            '--step', 'step1',
            '--transport', 'direct',
            '-p', '12345'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode == 0
        assert 'For step1/direct' in result.stdout
        assert 'just execute run_client.py' in result.stdout
    
    async def test_run_server_step1_direct_call(self):
        """Test run_server main_async function directly for coverage"""
        # This test calls the function directly for coverage
        args = ['--step', 'step1', '--transport', 'direct', '-p', '12345']
        with pytest.raises(SystemExit) as exc_info:
            await server_main_async(args)
        assert exc_info.value.code == 0
    
    
    def test_run_server_missing_port_and_uri(self):
        """Test run_server.py without port or uri (should fail)"""
        result = subprocess.run([
            sys.executable, str(self.run_server_script),
            '--step', 'step2',
            '--transport', 'grpc',
            '-d', str(self.db_path)
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode != 0
        assert 'step2 transports require either --port or --uri' in result.stderr
    
    def test_run_server_invalid_transport(self):
        """Test run_server.py with invalid transport"""
        result = subprocess.run([
            sys.executable, str(self.run_server_script),
            '--step', 'step2',
            '--transport', 'invalid_transport',
            '-p', '12345'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode != 0
        assert 'Invalid transport' in result.stderr
    
    async def test_run_server_missing_port_direct_call(self):
        """Test run_server main_async function with missing port (should fail)"""
        args = ['--step', 'step2', '--transport', 'grpc', '-d', str(self.db_path)]
        with pytest.raises(SystemExit):
            await server_main_async(args)


@pytest.mark.integration
class TestCLIDirectFunctionCalls:
    """Additional coverage tests using direct function calls"""
    
    def setup_method(self):
        """Set up test database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)
        
    def teardown_method(self):
        """Clean up test database after each test"""
        if self.db_path.exists():
            os.unlink(self.db_path)
    
    async def test_client_invalid_transport_direct(self):
        """Test run_client with invalid transport via direct call"""
        args = ['--step', 'step2', '--transport', 'invalid_transport']
        with pytest.raises(SystemExit):
            await client_main_async(args)
    
    async def test_client_missing_step_direct(self):
        """Test run_client with missing step argument via direct call"""
        args = ['--transport', 'direct']
        with pytest.raises(SystemExit):
            await client_main_async(args)
    
    async def test_client_missing_transport_direct(self):
        """Test run_client with missing transport argument via direct call"""
        args = ['--step', 'step1']
        with pytest.raises(SystemExit):
            await client_main_async(args)
    
    async def test_client_help_direct(self):
        """Test run_client --help via direct call"""
        args = ['--help']
        with pytest.raises(SystemExit) as exc_info:
            await client_main_async(args)
        assert exc_info.value.code == 0
    
    async def test_server_help_direct(self):
        """Test run_server --help via direct call"""
        args = ['--help']
        with pytest.raises(SystemExit) as exc_info:
            await server_main_async(args)
        assert exc_info.value.code == 0
    
    async def test_server_invalid_transport_direct(self):
        """Test run_server with invalid transport via direct call"""
        args = ['--step', 'step2', '--transport', 'invalid_transport', '-p', '12345']
        with pytest.raises(SystemExit):
            await server_main_async(args)


@pytest.mark.integration
@pytest.mark.skipif(not HAS_GRPC, reason="grpc not installed")
class TestCLIClientServerIntegration:
    """End-to-end integration tests with both client and server CLI tools"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)
        self.src_dir = Path(__file__).parent.parent / "src"
        self.run_client_script = self.src_dir / "cli" / "run_client.py"
        self.run_server_script = self.src_dir / "cli" / "run_server.py"
        self.server_process = None
        self.port = get_free_port()
        
    def teardown_method(self):
        """Clean up test environment"""
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    self.server_process.kill()
                    self.server_process.wait(timeout=2)
                except (subprocess.TimeoutExpired, ProcessLookupError):
                    pass
        
        if self.db_path.exists():
            os.unlink(self.db_path)
    
    def test_grpc_client_server_integration(self):
        """Test gRPC client-server integration via CLI tools"""
        # Start server in background
        self.server_process = subprocess.Popen([
            sys.executable, str(self.run_server_script),
            '--step', 'step2',
            '--transport', 'grpc',
            '-d', str(self.db_path),
            '-p', str(self.port)
        ], cwd=str(self.src_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Give server time to start
        time.sleep(2)
        
        # Check if server started successfully
        if self.server_process.poll() is not None:
            stdout, stderr = self.server_process.communicate()
            pytest.fail(f"Server failed to start. STDOUT: {stdout.decode()}, STDERR: {stderr.decode()}")
        
        # Run client
        client_result = subprocess.run([
            sys.executable, str(self.run_client_script),
            '--step', 'step2',
            '--transport', 'grpc',
            '-d', str(self.db_path),
            '-p', str(self.port)
        ], capture_output=True, text=True, cwd=str(self.src_dir), timeout=15)
        
        # Verify client ran successfully
        assert client_result.returncode == 0, f"Client failed. STDERR: {client_result.stderr}"
        assert 'Creating customer' in client_result.stdout
        assert 'All banking operations completed successfully' in client_result.stdout


@pytest.mark.integration
class TestCLIArgParsing:
    """Test CLI argument parsing edge cases"""
    
    def setup_method(self):
        """Set up test environment"""
        self.src_dir = Path(__file__).parent.parent / "src"
        self.run_client_script = self.src_dir / "cli" / "run_client.py"
        self.run_server_script = self.src_dir / "cli" / "run_server.py"
    
    def test_client_short_args(self):
        """Test run_client.py with short argument forms"""
        # Test with invalid transport to avoid actually running
        result = subprocess.run([
            sys.executable, str(self.run_client_script),
            '-s', 'step2',
            '-t', 'invalid',  # Will fail validation
            '-d', 'test.db',
            '-p', '12345'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        # Should fail on transport validation, not argument parsing
        assert 'Invalid transport' in result.stderr
    
    def test_client_long_args(self):
        """Test run_client.py with long argument forms"""
        # Test with invalid transport to avoid actually running
        result = subprocess.run([
            sys.executable, str(self.run_client_script),
            '--step', 'step2',
            '--transport', 'invalid',  # Will fail validation
            '--database', 'test.db',
            '--port', '12345'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        # Should fail on transport validation, not argument parsing
        assert 'Invalid transport' in result.stderr
    
    def test_server_short_args(self):
        """Test run_server.py with short argument forms"""
        # Test with step1 which has special handling
        result = subprocess.run([
            sys.executable, str(self.run_server_script),
            '-s', 'step1',
            '-t', 'direct',
            '-d', 'test.db',
            '-p', '12345'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode == 0
        assert 'For step1/direct' in result.stdout
    
    def test_server_long_args(self):
        """Test run_server.py with long argument forms"""
        # Test with step1 which has special handling
        result = subprocess.run([
            sys.executable, str(self.run_server_script),
            '--step', 'step1',
            '--transport', 'direct',
            '--database', 'test.db',
            '--port', '12345'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode == 0
        assert 'For step1/direct' in result.stdout


@pytest.mark.integration
class TestCLIErrorHandling:
    """Test CLI error handling and edge cases"""
    
    def setup_method(self):
        """Set up test environment"""
        self.src_dir = Path(__file__).parent.parent / "src"
        self.run_client_script = self.src_dir / "cli" / "run_client.py"
        self.run_server_script = self.src_dir / "cli" / "run_server.py"
    
    def test_client_invalid_port_type(self):
        """Test run_client.py with invalid port type"""
        result = subprocess.run([
            sys.executable, str(self.run_client_script),
            '--step', 'step2',
            '--transport', 'grpc',
            '-p', 'not_a_number'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode != 0
        assert 'invalid' in result.stderr or 'error' in result.stderr
    
    def test_server_invalid_port_type(self):
        """Test run_server.py with invalid port type"""
        result = subprocess.run([
            sys.executable, str(self.run_server_script),
            '--step', 'step2',
            '--transport', 'grpc',
            '-p', 'not_a_number'
        ], capture_output=True, text=True, cwd=str(self.src_dir))
        
        assert result.returncode != 0
        assert 'invalid' in result.stderr or 'error' in result.stderr
    
    def test_client_nonexistent_database_path(self):
        """Test run_client.py with non-existent directory for database"""
        result = subprocess.run([
            sys.executable, str(self.run_client_script),
            '--step', 'step1',
            '--transport', 'direct',
            '-d', '/nonexistent/path/database.db'
        ], capture_output=True, text=True, cwd=str(self.src_dir), timeout=10)
        
        # Should handle gracefully or show appropriate error
        # The exact behavior depends on the database implementation
        assert result.returncode != 0 or 'All banking operations completed successfully' in result.stdout