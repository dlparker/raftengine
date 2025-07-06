import pytest
from abc import ABC
from decimal import Decimal
from datetime import timedelta, date
from unittest.mock import AsyncMock
from src.base.proxy_api import ProxyAPI
from src.transports.direct.proxy import ServerProxy, ServerWrapper
from src.base.server import Server
from src.base.client import Client
from src.base.datatypes import AccountType, Customer, Account


class TestProxyAPI:
    """Test the ProxyAPI abstract base class"""
    
    def test_proxy_api_is_abstract(self):
        """Test that ProxyAPI cannot be instantiated directly"""
        with pytest.raises(TypeError):
            ProxyAPI()
    
    def test_server_proxy_implements_proxy_api(self):
        """Test that ServerProxy properly implements ProxyAPI"""
        # This should work without errors
        server = Server()
        wrapper = ServerWrapper(server)
        proxy = ServerProxy(wrapper)
        
        # Verify it's an instance of ProxyAPI
        assert isinstance(proxy, ProxyAPI)
    
    def test_client_accepts_proxy_api(self):
        """Test that Client accepts any ProxyAPI implementation"""
        # Create a mock that implements ProxyAPI
        mock_proxy = AsyncMock(spec=ProxyAPI)
        
        # This should work without type errors
        client = Client(mock_proxy)
        assert client.server_proxy is mock_proxy
    
    @pytest.mark.asyncio
    async def test_client_uses_proxy_api_methods(self):
        """Test that Client correctly calls ProxyAPI methods"""
        # Create a mock proxy
        mock_proxy = AsyncMock(spec=ProxyAPI)
        client = Client(mock_proxy)
        
        # Set up return values
        expected_customer = Customer(
            cust_id=1, first_name="Test", last_name="User", 
            address="123 Test St", accounts=[], 
            create_time=None, update_time=None
        )
        mock_proxy.create_customer.return_value = expected_customer
        
        # Call client method
        result = await client.create_customer("Test", "User", "123 Test St")
        
        # Verify proxy method was called correctly
        mock_proxy.create_customer.assert_called_once_with("Test", "User", "123 Test St")
        assert result == expected_customer
    
    def test_proxy_api_method_signatures(self):
        """Test that ProxyAPI has all required methods with correct signatures"""
        # Get all abstract methods from ProxyAPI
        abstract_methods = ProxyAPI.__abstractmethods__
        
        expected_methods = {
            'create_customer', 'create_account', 'deposit', 'withdraw', 
            'transfer', 'cash_check', 'list_accounts', 'get_accounts', 
            'list_statements', 'advance_time'
        }
        
        assert abstract_methods == expected_methods
    
    def test_server_proxy_implements_all_methods(self):
        """Test that ServerProxy implements all abstract methods"""
        server = Server()
        wrapper = ServerWrapper(server)
        proxy = ServerProxy(wrapper)
        
        # Check that all abstract methods are implemented
        for method_name in ProxyAPI.__abstractmethods__:
            assert hasattr(proxy, method_name)
            method = getattr(proxy, method_name)
            assert callable(method)
    
    @pytest.mark.asyncio
    async def test_full_stack_with_proxy_api(self):
        """Test the full stack works with ProxyAPI typing"""
        # Create full stack
        server = Server()
        wrapper = ServerWrapper(server)
        proxy: ProxyAPI = ServerProxy(wrapper)  # Type annotation to verify
        client = Client(proxy)
        
        # Test basic operation
        customer = await client.create_customer("API", "Test", "456 Interface Ave")
        assert isinstance(customer, Customer)
        assert customer.first_name == "API"
        assert customer.last_name == "Test"
    
    def test_proxy_api_inheritance_chain(self):
        """Test the inheritance chain is correctly set up"""
        server = Server()
        wrapper = ServerWrapper(server)
        proxy = ServerProxy(wrapper)
        
        # Check inheritance
        assert isinstance(proxy, ProxyAPI)
        assert isinstance(proxy, ServerProxy)
        assert issubclass(ServerProxy, ProxyAPI)
        
        # Check that ProxyAPI is abstract
        assert ABC in ProxyAPI.__mro__


class MockProxyImplementation(ProxyAPI):
    """A mock implementation of ProxyAPI for testing"""
    
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        return Customer(cust_id=999, first_name=first_name, last_name=last_name, 
                       address=address, accounts=[], create_time=None, update_time=None)
    
    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        return Account(account_id=999, account_type=account_type, customer_id=customer_id,
                      balance=Decimal('0.00'), create_time=None, update_time=None)
    
    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        return amount
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        return Decimal('0.00')
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal):
        return {"from_balance": Decimal('0.00'), "to_balance": amount}
    
    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        return Decimal('0.00')
    
    async def list_accounts(self):
        return []
    
    async def get_accounts(self, customer_id: str):
        return []
    
    async def list_statements(self, account_id: int):
        return []
    
    async def advance_time(self, delta_time: timedelta) -> None:
        pass


class TestMockProxyImplementation:
    """Test using a custom ProxyAPI implementation"""
    
    @pytest.mark.asyncio
    async def test_custom_proxy_implementation(self):
        """Test that custom ProxyAPI implementations work with Client"""
        mock_proxy = MockProxyImplementation()
        client = Client(mock_proxy)
        
        # Test customer creation
        customer = await client.create_customer("Mock", "User", "789 Mock St")
        assert customer.cust_id == 999
        assert customer.first_name == "Mock"
        assert customer.last_name == "User"
        
        # Test account creation
        account = await client.create_account("User,Mock", AccountType.SAVINGS)
        assert account.account_id == 999
        assert account.account_type == AccountType.SAVINGS
        
        # Test deposit
        balance = await client.deposit(1, Decimal('100.00'))
        assert balance == Decimal('100.00')
    
    def test_mock_proxy_is_proxy_api(self):
        """Test that custom implementation is recognized as ProxyAPI"""
        mock_proxy = MockProxyImplementation()
        assert isinstance(mock_proxy, ProxyAPI)