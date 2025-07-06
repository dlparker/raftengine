import pytest
from unittest.mock import AsyncMock, Mock
from decimal import Decimal
from datetime import timedelta, date
from src.base.client import Client
from src.base.datatypes import AccountType, Customer, Account


class TestClient:
    
    @pytest.fixture
    def mock_server_proxy(self):
        """Create a mock ServerProxy for testing"""
        return AsyncMock()
    
    @pytest.fixture
    def client(self, mock_server_proxy):
        """Create a Client instance with mocked ServerProxy"""
        return Client(mock_server_proxy)
    
    @pytest.mark.asyncio
    async def test_create_customer(self, client, mock_server_proxy):
        """Test create_customer delegates to ServerProxy"""
        expected_customer = Customer(
            cust_id=1,
            first_name="John",
            last_name="Doe", 
            address="123 Main St",
            accounts=[],
            create_time=None,
            update_time=None
        )
        mock_server_proxy.create_customer.return_value = expected_customer
        
        result = await client.create_customer("John", "Doe", "123 Main St")
        
        mock_server_proxy.create_customer.assert_called_once_with("John", "Doe", "123 Main St")
        assert result == expected_customer
    
    @pytest.mark.asyncio
    async def test_create_account(self, client, mock_server_proxy):
        """Test create_account delegates to ServerProxy"""
        expected_account = Account(
            account_id=1,
            account_type=AccountType.CHECKING,
            customer_id="Doe,John",
            balance=Decimal('0.00'),
            create_time=None,
            update_time=None
        )
        mock_server_proxy.create_account.return_value = expected_account
        
        result = await client.create_account("Doe,John", AccountType.CHECKING)
        
        mock_server_proxy.create_account.assert_called_once_with("Doe,John", AccountType.CHECKING)
        assert result == expected_account
    
    @pytest.mark.asyncio
    async def test_deposit(self, client, mock_server_proxy):
        """Test deposit delegates to ServerProxy"""
        mock_server_proxy.deposit.return_value = Decimal('150.00')
        
        result = await client.deposit(1, Decimal('150.00'))
        
        mock_server_proxy.deposit.assert_called_once_with(1, Decimal('150.00'))
        assert result == Decimal('150.00')
    
    @pytest.mark.asyncio
    async def test_withdraw(self, client, mock_server_proxy):
        """Test withdraw delegates to ServerProxy"""
        mock_server_proxy.withdraw.return_value = Decimal('75.00')
        
        result = await client.withdraw(1, Decimal('75.00'))
        
        mock_server_proxy.withdraw.assert_called_once_with(1, Decimal('75.00'))
        assert result == Decimal('75.00')
    
    @pytest.mark.asyncio
    async def test_transfer(self, client, mock_server_proxy):
        """Test transfer delegates to ServerProxy"""
        expected_result = {"from_balance": Decimal('50.00'), "to_balance": Decimal('100.00')}
        mock_server_proxy.transfer.return_value = expected_result
        
        result = await client.transfer(1, 2, Decimal('50.00'))
        
        mock_server_proxy.transfer.assert_called_once_with(1, 2, Decimal('50.00'))
        assert result == expected_result
    
    @pytest.mark.asyncio
    async def test_transfer_insufficient_funds(self, client, mock_server_proxy):
        """Test transfer returns None when insufficient funds"""
        mock_server_proxy.transfer.return_value = None
        
        result = await client.transfer(1, 2, Decimal('1000.00'))
        
        mock_server_proxy.transfer.assert_called_once_with(1, 2, Decimal('1000.00'))
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cash_check(self, client, mock_server_proxy):
        """Test cash_check delegates to ServerProxy"""
        mock_server_proxy.cash_check.return_value = Decimal('25.00')
        
        result = await client.cash_check(1, Decimal('25.00'))
        
        mock_server_proxy.cash_check.assert_called_once_with(1, Decimal('25.00'))
        assert result == Decimal('25.00')
    
    @pytest.mark.asyncio
    async def test_list_accounts(self, client, mock_server_proxy):
        """Test list_accounts delegates to ServerProxy"""
        expected_accounts = [
            Account(account_id=1, account_type=AccountType.CHECKING, customer_id="Doe,John", 
                   balance=Decimal('100.00'), create_time=None, update_time=None),
            Account(account_id=2, account_type=AccountType.SAVINGS, customer_id="Doe,John",
                   balance=Decimal('500.00'), create_time=None, update_time=None)
        ]
        mock_server_proxy.list_accounts.return_value = expected_accounts
        
        result = await client.list_accounts()
        
        mock_server_proxy.list_accounts.assert_called_once_with()
        assert result == expected_accounts
    
    @pytest.mark.asyncio
    async def test_get_accounts(self, client, mock_server_proxy):
        """Test get_accounts delegates to ServerProxy"""
        expected_account_ids = [1, 2, 3]
        mock_server_proxy.get_accounts.return_value = expected_account_ids
        
        result = await client.get_accounts("Doe,John")
        
        mock_server_proxy.get_accounts.assert_called_once_with("Doe,John")
        assert result == expected_account_ids
    
    @pytest.mark.asyncio
    async def test_list_statements(self, client, mock_server_proxy):
        """Test list_statements delegates to ServerProxy"""
        expected_dates = [date(2024, 1, 31), date(2024, 2, 29)]
        mock_server_proxy.list_statements.return_value = expected_dates
        
        result = await client.list_statements(1)
        
        mock_server_proxy.list_statements.assert_called_once_with(1)
        assert result == expected_dates
    
    @pytest.mark.asyncio
    async def test_advance_time(self, client, mock_server_proxy):
        """Test advance_time delegates to ServerProxy"""
        delta = timedelta(hours=2)
        mock_server_proxy.advance_time.return_value = None
        
        result = await client.advance_time(delta)
        
        mock_server_proxy.advance_time.assert_called_once_with(delta)
        assert result is None
    
    def test_client_constructor(self):
        """Test Client constructor stores server_proxy reference"""
        mock_proxy = Mock()
        client = Client(mock_proxy)
        
        assert client.server_proxy is mock_proxy
    
    @pytest.mark.asyncio
    async def test_client_propagates_exceptions(self, client, mock_server_proxy):
        """Test that Client propagates exceptions from ServerProxy"""
        mock_server_proxy.create_customer.side_effect = ValueError("Invalid customer data")
        
        with pytest.raises(ValueError, match="Invalid customer data"):
            await client.create_customer("", "", "")
    
    @pytest.mark.asyncio
    async def test_client_propagates_account_not_found(self, client, mock_server_proxy):
        """Test that Client propagates account not found errors"""
        mock_server_proxy.deposit.side_effect = ValueError("Account 999 not found")
        
        with pytest.raises(ValueError, match="Account 999 not found"):
            await client.deposit(999, Decimal('100.00'))
    
    @pytest.mark.asyncio
    async def test_client_propagates_customer_not_found(self, client, mock_server_proxy):
        """Test that Client propagates customer not found errors"""
        mock_server_proxy.create_account.side_effect = ValueError("Customer NonExistent not found")
        
        with pytest.raises(ValueError, match="Customer NonExistent not found"):
            await client.create_account("NonExistent", AccountType.CHECKING)