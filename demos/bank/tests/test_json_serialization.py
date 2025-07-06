import pytest
import json
from decimal import Decimal
from datetime import datetime, date, timedelta
from src.transports.json_helpers import BankJSONEncoder, bank_json_decoder, bank_json_dumps, bank_json_loads
from src.base.datatypes import AccountType


class TestJSONSerialization:
    """Test custom JSON encoder/decoder for banking data types"""
    
    def test_datetime_serialization(self):
        """Test datetime object serialization and deserialization"""
        test_datetime = datetime(2024, 3, 15, 14, 30, 45, 123456)
        
        # Serialize
        json_str = json.dumps(test_datetime, cls=BankJSONEncoder)
        expected = '{"__type__": "datetime", "value": "2024-03-15T14:30:45.123456"}'
        assert json_str == expected
        
        # Deserialize
        result = json.loads(json_str, object_hook=bank_json_decoder)
        assert result == test_datetime
        assert isinstance(result, datetime)
    
    def test_date_serialization(self):
        """Test date object serialization and deserialization"""
        test_date = date(2024, 12, 25)
        
        # Serialize
        json_str = json.dumps(test_date, cls=BankJSONEncoder)
        expected = '{"__type__": "date", "value": "2024-12-25"}'
        assert json_str == expected
        
        # Deserialize
        result = json.loads(json_str, object_hook=bank_json_decoder)
        assert result == test_date
        assert isinstance(result, date)
    
    def test_timedelta_serialization(self):
        """Test timedelta object serialization and deserialization"""
        test_delta = timedelta(days=5, hours=3, minutes=30, seconds=45)
        
        # Serialize
        json_str = json.dumps(test_delta, cls=BankJSONEncoder)
        total_seconds = test_delta.total_seconds()
        expected = f'{{"__type__": "timedelta", "value": {total_seconds}}}'
        assert json_str == expected
        
        # Deserialize
        result = json.loads(json_str, object_hook=bank_json_decoder)
        assert result == test_delta
        assert isinstance(result, timedelta)
    
    def test_decimal_serialization(self):
        """Test Decimal object serialization and deserialization"""
        test_decimal = Decimal('123.456789')
        
        # Serialize
        json_str = json.dumps(test_decimal, cls=BankJSONEncoder)
        expected = '{"__type__": "Decimal", "value": "123.456789"}'
        assert json_str == expected
        
        # Deserialize
        result = json.loads(json_str, object_hook=bank_json_decoder)
        assert result == test_decimal
        assert isinstance(result, Decimal)
    
    def test_account_type_serialization(self):
        """Test AccountType enum serialization and deserialization"""
        test_account_type = AccountType.CHECKING
        
        # Serialize
        json_str = bank_json_dumps(test_account_type)
        expected = '{"__type__": "AccountType", "value": "checking"}'
        assert json_str == expected
        
        # Deserialize
        result = bank_json_loads(json_str)
        assert result == test_account_type
        assert isinstance(result, AccountType)
        assert result == AccountType.CHECKING
    
    def test_complex_nested_serialization(self):
        """Test serialization of complex nested structures with banking types"""
        complex_data = {
            "command": "create_account",
            "args": {
                "customer_id": "Doe,John",
                "account_type": AccountType.SAVINGS,
                "initial_deposit": Decimal('1000.50'),
                "created_at": datetime(2024, 1, 15, 10, 30, 0),
                "valid_until": date(2024, 12, 31),
                "processing_delay": timedelta(minutes=5)
            },
            "metadata": {
                "timestamp": datetime.now(),
                "amounts": [Decimal('100.00'), Decimal('250.75'), Decimal('999.99')]
            }
        }
        
        # Serialize
        json_str = bank_json_dumps(complex_data)
        
        # Deserialize
        result = bank_json_loads(json_str)
        
        # Verify structure preserved
        assert result["command"] == "create_account"
        assert result["args"]["customer_id"] == "Doe,John"
        assert result["args"]["account_type"] == AccountType.SAVINGS
        assert result["args"]["initial_deposit"] == Decimal('1000.50')
        assert result["args"]["created_at"] == datetime(2024, 1, 15, 10, 30, 0)
        assert result["args"]["valid_until"] == date(2024, 12, 31)
        assert result["args"]["processing_delay"] == timedelta(minutes=5)
        
        # Verify types are correct
        assert isinstance(result["args"]["account_type"], AccountType)
        assert isinstance(result["args"]["initial_deposit"], Decimal)
        assert isinstance(result["args"]["created_at"], datetime)
        assert isinstance(result["args"]["valid_until"], date)
        assert isinstance(result["args"]["processing_delay"], timedelta)
        
        # Verify list of Decimals
        assert len(result["metadata"]["amounts"]) == 3
        assert all(isinstance(amt, Decimal) for amt in result["metadata"]["amounts"])
        assert result["metadata"]["amounts"][0] == Decimal('100.00')
    
    def test_regular_data_unaffected(self):
        """Test that regular JSON data types are not affected by custom encoder"""
        regular_data = {
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"key": "value"}
        }
        
        # Serialize
        json_str = json.dumps(regular_data, cls=BankJSONEncoder)
        
        # Deserialize
        result = json.loads(json_str, object_hook=bank_json_decoder)
        
        # Should be identical
        assert result == regular_data
    
    def test_mixed_data_serialization(self):
        """Test serialization of mixed regular and banking data types"""
        mixed_data = {
            "customer_name": "John Doe",
            "account_balance": Decimal('500.00'),
            "last_login": datetime(2024, 3, 15, 9, 30, 0),
            "account_count": 2,
            "is_premium": True,
            "account_types": [AccountType.CHECKING, AccountType.SAVINGS],
            "session_timeout": timedelta(hours=2)
        }
        
        # Serialize and deserialize
        json_str = bank_json_dumps(mixed_data)
        result = bank_json_loads(json_str)
        
        # Verify all data preserved with correct types
        assert result["customer_name"] == "John Doe"
        assert result["account_balance"] == Decimal('500.00')
        assert isinstance(result["account_balance"], Decimal)
        assert result["last_login"] == datetime(2024, 3, 15, 9, 30, 0)
        assert isinstance(result["last_login"], datetime)
        assert result["account_count"] == 2
        assert result["is_premium"] is True
        assert len(result["account_types"]) == 2
        assert all(isinstance(at, AccountType) for at in result["account_types"])
        assert result["session_timeout"] == timedelta(hours=2)
        assert isinstance(result["session_timeout"], timedelta)
    
    def test_command_args_simulation(self):
        """Test serialization that simulates actual command arguments"""
        # This simulates what happens in the ServerWrapper
        command_data = {
            "command_name": "transfer",
            "args": {
                "from_account_id": 1,
                "to_account_id": 2,
                "amount": Decimal('150.75'),
                "timestamp": datetime.now(),
                "account_type": AccountType.CHECKING
            }
        }
        
        # Simulate the serialize/deserialize cycle in ServerWrapper
        serialized = bank_json_dumps(command_data)
        deserialized = bank_json_loads(serialized)
        
        # Verify the command can be executed with proper types
        assert deserialized["command_name"] == "transfer"
        assert isinstance(deserialized["args"]["amount"], Decimal)
        assert isinstance(deserialized["args"]["timestamp"], datetime)
        assert isinstance(deserialized["args"]["account_type"], AccountType)
        assert deserialized["args"]["from_account_id"] == 1
        assert deserialized["args"]["to_account_id"] == 2