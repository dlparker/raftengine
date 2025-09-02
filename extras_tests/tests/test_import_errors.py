import sys
import builtins

import pytest


real_import = builtins.__import__


def monkey_lmdb(name, globals=None, locals=None, fromlist=(), level=0):
    if name in ('lmdb',):
        raise ModuleNotFoundError(f"Mocked module not found {name}")
    return real_import(name, globals=globals, locals=locals, fromlist=fromlist, level=level)

def monkey_lmdb_log(name, globals=None, locals=None, fromlist=(), level=0):
    if name in ('raftengine.extras.lmdb_log',):
        raise ModuleNotFoundError(f"Mocked module not found {name}")
    return real_import(name, globals=globals, locals=locals, fromlist=fromlist, level=level)

def monkey_grpc(name, globals=None, locals=None, fromlist=(), level=0):
    if name in ('grpc'):
        raise ModuleNotFoundError(f"Mocked module not found {name}")
    return real_import(name, globals=globals, locals=locals, fromlist=fromlist, level=level)

def monkey_aiozmq(name, globals=None, locals=None, fromlist=(), level=0):
    if name in ('aiozmq'):
        raise ModuleNotFoundError(f"Mocked module not found {name}")
    return real_import(name, globals=globals, locals=locals, fromlist=fromlist, level=level)

def monkey_msgpack(name, globals=None, locals=None, fromlist=(), level=0):
    if name in ('msgpack'):
        raise ModuleNotFoundError(f"Mocked module not found {name}")
    return real_import(name, globals=globals, locals=locals, fromlist=fromlist, level=level)

def monkey_sqlite(name, globals=None, locals=None, fromlist=(), level=0):
    if name in ('raftengine.extras.sqlite_log'):
        raise ModuleNotFoundError(f"Mocked module not found {name}")
    return real_import(name, globals=globals, locals=locals, fromlist=fromlist, level=level)

async def test_lmdb_import_fail(monkeypatch):
    monkeypatch.delitem(sys.modules, 'lmdb', raising=False)
    monkeypatch.delitem(sys.modules, 'raftengine.extras.lmdb_log', raising=False)
    monkeypatch.setattr(builtins, '__import__', monkey_lmdb)
    with pytest.raises(Exception) as excinfo:
        from raftengine.extras.lmdb_log import LmdbLog
    assert "lmdb package not installed" in str(excinfo)

async def test_hybrid_import_fail_1(monkeypatch):
    monkeypatch.delitem(sys.modules, 'lmdb', raising=False)
    monkeypatch.delitem(sys.modules, 'raftengine.extras.hybrid_log', raising=False)
    monkeypatch.setattr(builtins, '__import__', monkey_lmdb)
    with pytest.raises(Exception) as excinfo:
        from raftengine.extras.hybrid_log import HybridLog
    assert "lmdb package not installed" in str(excinfo)

async def test_hybrid_import_fail_2(monkeypatch):
    monkeypatch.delitem(sys.modules, 'raftengine.extras.sqlite_log', raising=False)
    monkeypatch.delitem(sys.modules, 'raftengine.extras.hybrid_log', raising=False)
    monkeypatch.setattr(builtins, '__import__', monkey_sqlite)
    with pytest.raises(Exception) as excinfo:
        from raftengine.extras.hybrid_log import HybridLog
    assert "sqlite_log package not installed" in str(excinfo)

async def test_hybrid_import_fail_3(monkeypatch):
    monkeypatch.setitem(sys.modules, 'raftengine.extras.lmdb_log', None)
    monkeypatch.delitem(sys.modules, 'raftengine.extras.hybrid_log', raising=False)
    monkeypatch.setattr(builtins, '__import__', monkey_lmdb_log)
    with pytest.raises(Exception) as excinfo:
        from raftengine.extras.hybrid_log import HybridLog
    assert "lmdb_log package not installed" in str(excinfo)

async def test_aiozmq_import_fail_1(monkeypatch):
    monkeypatch.delitem(sys.modules, 'aiozmq', raising=False)
    monkeypatch.delitem(sys.modules, 'raftengine.extras.aiozmq_rpc', raising=False)
    monkeypatch.setattr(builtins, '__import__', monkey_aiozmq)
    with pytest.raises(Exception) as excinfo:
        from raftengine.extras.aiozmq_rpc import RPCClient
    assert "package not installed" in str(excinfo)

async def test_aiozmq_import_fail_2(monkeypatch):
    monkeypatch.delitem(sys.modules, 'msgpack', raising=False)
    monkeypatch.delitem(sys.modules, 'raftengine.extras.aiozmq_rpc', raising=False)
    monkeypatch.setattr(builtins, '__import__', monkey_msgpack)
    with pytest.raises(Exception) as excinfo:
        from raftengine.extras.aiozmq_rpc import RPCClient
    assert "package not installed" in str(excinfo)


async def test_grpc_import_fail_1(monkeypatch):
    monkeypatch.delitem(sys.modules, 'grpc', raising=False)
    monkeypatch.delitem(sys.modules, 'raftengine.extras.grpc_rpc', raising=False)
    monkeypatch.setattr(builtins, '__import__', monkey_grpc)
    with pytest.raises(Exception) as excinfo:
        from raftengine.extras.grpc_rpc import RPCClient
    assert "package not installed" in str(excinfo)
    
