#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
import json
from raftengine.deck.deck import Deck
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage,PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.snapshot import SnapShotMessage, SnapShotResponseMessage
from raftengine.messages.message_codec import MessageCodec
from raftengine.api.types import RoleName
from raftengine.api.log_api import LogRec
from dev_tools.pausing_cluster import PausingCluster, cluster_maker
from dev_tools.log_control import setup_logging
from raftengine_logs.sqlite_log import SqliteLog

log_control = setup_logging()
logger = logging.getLogger("test_code")

async def test_bogus_pilot(cluster_maker):
    """
    Ensures that Deck constructor rejects Pilot class that does
    not implement PilotAPI
    """
    cluster = cluster_maker(3)
    await cluster.test_trace.define_test("Testing Deck constructor with invalid Pilot", logger=logger)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    ts_1 = cluster.nodes[uri_1]
    class BadPilot:
        pass
    with pytest.raises(Exception):
        Deck(ts_1.cluster_init_config, ts_1.local_config, BadPilot())

async def test_shutdown_mis_order(cluster_maker):
    """
    Ensures that Deck constructor rejects Pilot class that does
    not implement PilotAPI
    """
    cluster = cluster_maker(3, use_log=SqliteLog)
    await cluster.test_trace.define_test("Testing shutdown out of order where log is closed before deck", logger=logger)
    cluster.set_configs()
    uri_1 = cluster.node_uris[0]
    ts_1 = cluster.nodes[uri_1]
    await ts_1.start()
    await ts_1.log.stop()
    await ts_1.deck.role.stop()

async def test_str_methods():
    """
    Ensures that __str__ methods of internal classes don't blow
    up when called, and that the result contains at least something
    of the expected information. Not much of a test, but the
    doesn't-blow-up part is useful.
    """
    assert str(RoleName.leader) == 'LEADER'
    assert "request_vote" in str(RequestVoteMessage('a','b', 0, 0, 0))
    assert "request_vote_response" in str(RequestVoteResponseMessage('a','b', 0, 0, 0, True))
    assert "v=True" in str(RequestVoteResponseMessage('a','b', 0, 0, 0, True))
    assert "v=False" in str(RequestVoteResponseMessage('a','b', 0, 0, 0, False))
    assert "append_entries" in str(AppendEntriesMessage('a','b', 0, 0, 0, entries=[]))
    assert "append_response" in str(AppendResponseMessage('a','b', 0, 0, 0, 0, True, 'a', 0))
    assert "s=True" in str(AppendResponseMessage('a','b', 0, 0, 0, 0, True, 'a', 0))
    assert "s=False" in str(AppendResponseMessage('a','b', 0, 0, 0, 0, False, 'a', 0))

async def test_enum_edges():
    
    rec = LogRec(index=1, term=1, command="foo", committed=True, applied=True)
    assert str(rec.code) == "CLIENT_COMMAND"
    

async def test_message_ops():

    from raftengine.messages.log_msg import LogMessage
    from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
    from raftengine.messages.cluster_change import MembershipChangeMessage, MembershipChangeResponseMessage, ChangeOp
    from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
    from raftengine.messages.pre_vote import PreVoteMessage, PreVoteResponseMessage
    from raftengine.messages.request_vote import RequestVoteMessage, RequestVoteResponseMessage

    rec_1 = LogRec(index=1, term=1, command="add 1", leader_id='mcpy://1', committed=True, applied=True)
    ae_1 = AppendEntriesMessage('mcpy://1', 'mcpy://2', term=1, prevLogIndex=0, prevLogTerm=0,
                               entries = [rec_1], commitIndex=0)
    # do the encode first so that it inserts a serial number
    jd1, sn1 = MessageCodec.encode_message(ae_1)
    re_1 = AppendResponseMessage('mcpy://2', 'mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0, maxIndex=1,
                                 success=True, leaderId='mcpy://1', original_serial=ae_1.serial_number)

    re_2 = AppendResponseMessage('mcpy://1', 'mcpy://3', term=1, prevLogIndex=0, prevLogTerm=0, maxIndex=1,
                                 success=True, leaderId='mcpy://1', original_serial=ae_1.serial_number + 1)

    jd2, sn2 = MessageCodec.encode_message(re_1)
    c_ae_1 = MessageCodec.decode_message(jd1)
    c_re_1 = MessageCodec.decode_message(jd2)
    
    assert c_re_1.is_reply_to(ae_1)
    assert re_1.is_reply_to(c_ae_1)
    assert not re_2.is_reply_to(c_ae_1)
    assert str(ae_1) == str(c_ae_1)
    assert str(re_1) == str(c_re_1)

    mc_1 = MembershipChangeMessage('mcpy://1', 'mcpy://2', op=ChangeOp.add, target_uri="mcpy://4")
    rmc_1 = MembershipChangeResponseMessage('mcpy://2', 'mcpy://1', op=ChangeOp.add, target_uri="mcpy://4", ok=True)

    mc_jd1, mc_sn1 = MessageCodec.encode_message(mc_1)
    rm_jd1, rm_sn1 = MessageCodec.encode_message(rmc_1)
    c_mc_1 = MessageCodec.decode_message(mc_jd1)
    c_rmc_1 = MessageCodec.decode_message(rm_jd1)
    assert str(mc_1) == str(c_mc_1)
    assert str(rmc_1) == str(c_rmc_1)
    assert c_rmc_1.is_reply_to(mc_1)
    rmc_2 = MembershipChangeResponseMessage('mcpy://3', 'mcpy://4', op=ChangeOp.add, target_uri="mcpy://4", ok=True)
    assert not  rmc_2.is_reply_to(mc_1)


    tpm_1 = TransferPowerMessage('mcpy://1', 'mcpy://2', term=1, prevLogIndex=0, prevLogTerm=0)
    tpr_1 = TransferPowerResponseMessage('mcpy://2', 'mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0, success=True)
    
    j_tpm_1, tpm_sn1 = MessageCodec.encode_message(tpm_1)
    j_tpr_1, tpr_sn1 = MessageCodec.encode_message(tpr_1)
    c_tpm_1 = MessageCodec.decode_message(j_tpm_1)
    c_tpr_1 = MessageCodec.decode_message(j_tpr_1)
    assert c_tpr_1.is_reply_to(tpm_1)
    assert tpr_1.is_reply_to(c_tpm_1)
    assert str(tpm_1) == str(c_tpm_1)
    assert str(tpr_1) == str(c_tpr_1)
    tpr_2 = TransferPowerResponseMessage('mcpy://3', 'mcpy://4', term=1, prevLogIndex=0, prevLogTerm=0, success=True)
    assert not tpr_2.is_reply_to(tpm_1)

 
    pvm_1 = PreVoteMessage('mcpy://1', 'mcpy://2', term=1, prevLogIndex=0, prevLogTerm=0)
    pvr_1 = PreVoteResponseMessage('mcpy://2', 'mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0, vote=True)
    
    j_pvm_1, pvm_sn1 = MessageCodec.encode_message(pvm_1)
    j_pvr_1, pvr_sn1 = MessageCodec.encode_message(pvr_1)
    c_pvm_1 = MessageCodec.decode_message(j_pvm_1)
    c_pvr_1 = MessageCodec.decode_message(j_pvr_1)
    assert c_pvr_1.is_reply_to(pvm_1)
    assert pvr_1.is_reply_to(c_pvm_1)
    assert str(pvm_1) == str(c_pvm_1)
    assert str(pvr_1) == str(c_pvr_1)

    rvm_1 = RequestVoteMessage('mcpy://1', 'mcpy://2', term=1, prevLogIndex=0, prevLogTerm=0)
    rvr_1 = RequestVoteResponseMessage('mcpy://2', 'mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0, vote=True)
    
    j_rvm_1, rvm_sn1 = MessageCodec.encode_message(rvm_1)
    j_rvr_1, rvr_sn1 = MessageCodec.encode_message(rvr_1)
    c_rvm_1 = MessageCodec.decode_message(j_rvm_1)
    c_rvr_1 = MessageCodec.decode_message(j_rvr_1)
    assert c_rvr_1.is_reply_to(rvm_1)
    assert rvr_1.is_reply_to(c_rvm_1)
    assert str(rvm_1) == str(c_rvm_1)
    assert str(rvr_1) == str(c_rvr_1)
    

    ssm = SnapShotMessage(sender='a', receiver='b', term=1, prevLogIndex=0, prevLogTerm=0,
                          leaderId="a", offset=0, done=True, data="[1,2]")
    assert "d=True" in str(ssm)

    ssmr = SnapShotResponseMessage(sender='b', receiver='a',term=1, prevLogIndex=0, prevLogTerm=0, offset=0, success=True)
    assert "s=True" in str(ssmr)
    assert ssmr.is_reply_to(ssm)


# LogController Tests - comprehensive coverage for library code

async def test_log_controller_basic():
    """Test basic LogController functionality"""
    from raftengine.deck.log_control import LogController

    saved_log_controller = LogController.controller
    LogController.controller = None
    with pytest.raises(Exception):
        LogController.get_controller()
    controller = LogController()
    assert LogController.controller is not None
    assert LogController.get_controller() == controller
    with pytest.raises(Exception):
        LogController.make_controller()
    with pytest.raises(Exception):
        LogController()
    LogController.controller = None
    LogController.make_controller()
    assert LogController.controller is not None
    
    assert controller.default_level == "ERROR"
    assert controller.default_handlers == ["stdout"]
    logger_count = len(controller.known_loggers) 
    handler_count = len(controller.known_handlers) 
    
    # Test with additional loggers
    additional_loggers = [("TestLogger", "Test logger description")]
    LogController.controller = None
    controller2 = LogController(additional_loggers=additional_loggers)
    assert len(controller2.known_loggers) == logger_count + 1
    assert "TestLogger" in controller2.known_loggers
    assert controller2.known_loggers["TestLogger"].description == "Test logger description"
    LogController.controller = saved_log_controller 
    
async def test_log_controller_logger_levels():
    """Test logger level management"""
    from raftengine.deck.log_control import LogController
    import logging
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Test setting logger levels with strings
    controller.set_logger_level("Leader", "DEBUG")
    assert controller.get_logger_level("Leader") == logging.DEBUG
    assert controller.known_loggers["Leader"].custom_level == "DEBUG"
    
    # Test setting logger levels with integers
    controller.set_logger_level("Follower", logging.INFO)
    assert controller.get_logger_level("Follower") == logging.INFO
    assert controller.known_loggers["Follower"].custom_level == "INFO"
    
    # Test setting default level
    controller.set_default_level("WARNING")
    assert controller.default_level == "WARNING"
    
    # Test setting default level with integer
    controller.set_default_level(logging.ERROR)
    assert controller.default_level == "ERROR"
    
    # Test that loggers with custom levels are not affected by default change
    controller.set_default_level("CRITICAL")
    assert controller.get_logger_level("Leader") == logging.DEBUG  # Still custom
    assert controller.get_logger_level("Deck") == logging.CRITICAL  # Changed to default
    LogController.controller = saved_log_controller 

async def test_log_controller_errors():
    """Test error handling in LogController"""
    from raftengine.deck.log_control import LogController
    import pytest
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Test invalid logger name
    with pytest.raises(ValueError, match="Unknown logger"):
        controller.set_logger_level("InvalidLogger", "DEBUG")
    
    with pytest.raises(ValueError, match="Unknown logger"):
        controller.get_logger_level("InvalidLogger")
    
    # Test invalid level
    with pytest.raises(ValueError, match="Invalid level"):
        controller.set_logger_level("Leader", "INVALID_LEVEL")
    
    with pytest.raises(ValueError, match="Invalid level"):
        controller.set_default_level("INVALID_LEVEL")
    LogController.controller = saved_log_controller 

async def test_log_controller_add_logger():
    """Test adding new loggers"""
    from raftengine.deck.log_control import LogController
    import logging
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Test adding logger with defaults
    controller.add_logger("CustomLogger", "Custom test logger")
    assert "CustomLogger" in controller.known_loggers
    assert controller.known_loggers["CustomLogger"].description == "Custom test logger"
    assert controller.known_loggers["CustomLogger"].handler_names == ["stdout"]
    assert controller.get_logger_level("CustomLogger") == logging.ERROR
    
    # Test adding logger with custom level
    controller.add_logger("CustomLogger2", "Another custom logger", level="DEBUG")
    assert controller.get_logger_level("CustomLogger2") == logging.DEBUG
    assert controller.known_loggers["CustomLogger2"].custom_level == "DEBUG"
    
    # Test adding logger with custom handlers
    controller.add_logger("top_level.CustomLogger3", "Third custom logger", handlers=["file"])
    assert controller.known_loggers["top_level.CustomLogger3"].handler_names == ["file"]
    assert controller.known_loggers["top_level"].handler_names == ["stdout"]
    LogController.controller = saved_log_controller 

async def test_log_controller_save_restore():
    """Test save and restore functionality"""
    from raftengine.deck.log_control import LogController
    import logging
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Set some custom levels
    controller.set_logger_level("Leader", "DEBUG")
    controller.set_logger_level("Follower", "INFO")
    original_leader_level = controller.get_logger_level("Leader")
    original_follower_level = controller.get_logger_level("Follower")
    
    # Save current state
    controller.save_current_levels()
    
    # Change levels
    controller.set_logger_level("Leader", "ERROR")
    controller.set_logger_level("Follower", "CRITICAL")
    assert controller.get_logger_level("Leader") == logging.ERROR
    assert controller.get_logger_level("Follower") == logging.CRITICAL
    
    # Restore original levels
    controller.restore_saved_levels()
    assert controller.get_logger_level("Leader") == original_leader_level
    assert controller.get_logger_level("Follower") == original_follower_level
    assert controller.known_loggers["Leader"].custom_level == "DEBUG"
    assert controller.known_loggers["Follower"].custom_level == "INFO"
    
    # Test error when restoring without saving
    with pytest.raises(RuntimeError, match="No saved levels to restore"):
        controller.restore_saved_levels()
    LogController.controller = saved_log_controller 

async def test_handler_def():
    """Test HandlerDef dataclass"""
    from raftengine.deck.log_control import HandlerDef
    
    # Test basic handler definition
    handler = HandlerDef(
        name="test_handler",
        description="Test handler",
        handler_type="stream",
        level="DEBUG",
        formatter="standard",
        stream="ext://sys.stdout",
        handler_class="logging.StreamHandler"
    )
    
    assert handler.name == "test_handler"
    assert handler.description == "Test handler"
    assert handler.handler_type == "stream"
    assert handler.level == "DEBUG"
    assert handler.formatter == "standard"
    assert handler.stream == "ext://sys.stdout"
    assert handler.handler_class == "logging.StreamHandler"
    assert handler.mode == "a"  # default
    assert handler.encoding == "utf-8"  # default
    assert handler.extra_config == {}  # default
    
    # Test with extra config
    handler2 = HandlerDef(
        name="test_handler2",
        description="Test handler 2",
        handler_type="custom",
        extra_config={"custom_param": "value"}
    )
    assert handler2.extra_config == {"custom_param": "value"}

async def test_logger_def():
    """Test LoggerDef dataclass"""
    from raftengine.deck.log_control import LoggerDef
    
    # Test basic logger definition
    logger_def = LoggerDef(
        name="test_logger",
        description="Test logger",
        custom_level="DEBUG",
        propagate=True,
        handler_names=["stdout", "file"]
    )
    
    assert logger_def.name == "test_logger"
    assert logger_def.description == "Test logger"
    assert logger_def.custom_level == "DEBUG"
    assert logger_def.propagate == True
    assert logger_def.handler_names == ["stdout", "file"]
    
    # Test defaults
    logger_def2 = LoggerDef("test_logger2", "Test logger 2")
    assert logger_def2.custom_level is None
    assert logger_def2.propagate == False
    assert logger_def2.handler_names == []

async def test_handler_management():
    """Test handler management functionality"""
    from raftengine.deck.log_control import LogController
    import pytest
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Test listing handlers
    handlers = controller.list_handlers()
    assert "stdout" in handlers
    assert "file" in handlers
    assert len(handlers) == 2
    
    # Test getting handler info
    stdout_handler = controller.get_handler_info("stdout")
    assert stdout_handler.name == "stdout"
    assert stdout_handler.handler_type == "stream"
    assert stdout_handler.stream == "ext://sys.stdout"
    
    # Test adding handler
    controller.add_handler("test_handler", "stream", "Test stream handler", 
                          level="INFO", stream="ext://sys.stderr")
    assert "test_handler" in controller.list_handlers()
    
    test_handler = controller.get_handler_info("test_handler")
    assert test_handler.description == "Test stream handler"
    assert test_handler.level == "INFO"
    assert test_handler.stream == "ext://sys.stderr"
    
    # Test adding file handler
    controller.add_handler("test_file", "file", "Test file handler",
                          filename="test.log", mode="w")
    file_handler = controller.get_handler_info("test_file")
    assert file_handler.filename == "test.log"
    assert file_handler.mode == "w"
    
    # Test adding custom handler
    controller.add_handler("test_custom", "custom", "Test custom handler",
                          handler_class="logging.handlers.RotatingFileHandler",
                          maxBytes=1024, backupCount=3)
    custom_handler = controller.get_handler_info("test_custom")
    assert custom_handler.handler_class == "logging.handlers.RotatingFileHandler"
    assert custom_handler.extra_config["maxBytes"] == 1024
    assert custom_handler.extra_config["backupCount"] == 3
    
    # Test error cases
    with pytest.raises(ValueError, match="Handler .* already exists"):
        controller.add_handler("stdout", "stream", "Duplicate handler")
    
    with pytest.raises(ValueError, match="Handler .* not found"):
        controller.get_handler_info("nonexistent")
    
    # Test removing handler
    controller.remove_handler("test_handler")
    assert "test_handler" not in controller.list_handlers()
    
    with pytest.raises(ValueError, match="Handler .* not found"):
        controller.remove_handler("nonexistent")
    LogController.controller = saved_log_controller 

async def test_handler_creation_utilities():
    """Test handler creation utility methods"""
    from raftengine.deck.log_control import LogController
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Test create_stdout_handler
    controller.create_stdout_handler("new_stdout", level="WARNING", description="New stdout handler")
    handler = controller.get_handler_info("new_stdout")
    assert handler.handler_type == "stream"
    assert handler.level == "WARNING"
    assert handler.description == "New stdout handler"
    assert handler.stream == "ext://sys.stdout"
    
    # Test create_file_handler
    controller.create_file_handler("new_file", "debug.log", level="DEBUG", 
                                  mode="w", encoding="utf-8", description="New file handler")
    handler = controller.get_handler_info("new_file")
    assert handler.handler_type == "file"
    assert handler.filename == "debug.log"
    assert handler.mode == "w"
    assert handler.encoding == "utf-8"
    assert handler.description == "New file handler"
    
    # Test create_custom_handler
    controller.create_custom_handler("new_custom", "logging.handlers.SysLogHandler",
                                    level="INFO", description="New custom handler",
                                    address=("localhost", 514))
    handler = controller.get_handler_info("new_custom")
    assert handler.handler_type == "custom"
    assert handler.handler_class == "logging.handlers.SysLogHandler"
    assert handler.level == "INFO"
    assert handler.description == "New custom handler"
    assert handler.extra_config["address"] == ("localhost", 514)
    LogController.controller = saved_log_controller 

async def test_logger_handler_association():
    """Test logger-handler association methods"""
    from raftengine.deck.log_control import LogController
    import pytest
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Test getting logger handlers
    leader_handlers = controller.get_logger_handlers("Leader")
    assert leader_handlers == ["stdout"]
    
    # Test assigning handler to logger
    controller.assign_handler_to_logger("Leader", "file")
    leader_handlers = controller.get_logger_handlers("Leader")
    assert "file" in leader_handlers
    assert "stdout" in leader_handlers
    
    # Test removing handler from logger
    controller.remove_handler_from_logger("Leader", "file")
    leader_handlers = controller.get_logger_handlers("Leader")
    assert "file" not in leader_handlers
    assert "stdout" in leader_handlers
    
    # Test setting all handlers for logger
    controller.set_logger_handlers("Leader", ["file"])
    leader_handlers = controller.get_logger_handlers("Leader")
    assert leader_handlers == ["file"]
    
    # Test error cases
    with pytest.raises(ValueError, match="Logger .* not found"):
        controller.assign_handler_to_logger("NonExistentLogger", "stdout")
    
    with pytest.raises(ValueError, match="Handler .* not found"):
        controller.assign_handler_to_logger("Leader", "NonExistentHandler")
    
    with pytest.raises(ValueError, match="Logger .* not found"):
        controller.remove_handler_from_logger("NonExistentLogger", "stdout")
    
    with pytest.raises(ValueError, match="Logger .* not found"):
        controller.set_logger_handlers("NonExistentLogger", ["stdout"])
    
    with pytest.raises(ValueError, match="Handler .* not found"):
        controller.set_logger_handlers("Leader", ["NonExistentHandler"])
    
    with pytest.raises(ValueError, match="Logger .* not found"):
        controller.get_logger_handlers("NonExistentLogger")
    LogController.controller = saved_log_controller 

async def test_default_handlers():
    """Test default handler management"""
    from raftengine.deck.log_control import LogController
    import pytest
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Test getting default handlers
    default_handlers = controller.get_default_handlers()
    assert default_handlers == ["stdout"]
    
    # Test setting default handlers
    controller.set_default_handlers(["file", "stdout"])
    default_handlers = controller.get_default_handlers()
    assert default_handlers == ["file", "stdout"]
    
    # Test that new loggers use default handlers
    controller.add_logger("NewLogger", "New test logger")
    new_logger_handlers = controller.get_logger_handlers("NewLogger")
    assert new_logger_handlers == ["file", "stdout"]
    
    # Test error with invalid handler
    with pytest.raises(ValueError, match="Handler .* not found"):
        controller.set_default_handlers(["NonExistentHandler"])
    LogController.controller = saved_log_controller 

async def test_add_logger_errors():
    """Test error cases when adding loggers"""
    from raftengine.deck.log_control import LogController
    import pytest
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Test adding logger with invalid handler
    with pytest.raises(ValueError, match="Handler .* not found"):
        controller.add_logger("TestLogger", "Test", handlers=["NonExistentHandler"])
    LogController.controller = saved_log_controller 

async def test_temporary_log_control():
    """Test TemporaryLogControl context manager"""
    from raftengine.deck.log_control import LogController, TemporaryLogControl
    import logging
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Set initial levels
    controller.set_logger_level("Leader", "DEBUG")
    controller.set_logger_level("Follower", "INFO")
    controller.set_logger_level("Candidate", "WARNING")
    
    original_leader_level = controller.get_logger_level("Leader")
    original_follower_level = controller.get_logger_level("Follower")
    original_candidate_level = controller.get_logger_level("Candidate")
    
    # Test basic temporary control
    with TemporaryLogControl(controller, keep_active=["Leader"], silence_level="ERROR"):
        # Leader should stay at DEBUG, others should be silenced to ERROR
        assert controller.get_logger_level("Leader") == logging.DEBUG
        assert controller.get_logger_level("Follower") == logging.ERROR
        assert controller.get_logger_level("Candidate") == logging.ERROR
    
    # After context, levels should be restored
    assert controller.get_logger_level("Leader") == original_leader_level
    assert controller.get_logger_level("Follower") == original_follower_level
    assert controller.get_logger_level("Candidate") == original_candidate_level
    
    # Test with temporary handlers
    controller.add_handler("temp_handler", "stream", "Temporary handler", stream="ext://sys.stderr")
    temp_handlers = {"Leader": ["temp_handler"]}
    
    with TemporaryLogControl(controller, temporary_handlers=temp_handlers):
        # Leader should have temporary handler
        assert controller.get_logger_handlers("Leader") == ["temp_handler"]
    
    # After context, handlers should be restored
    assert controller.get_logger_handlers("Leader") == ["stdout"]
    
    # Test with both keep_active and temporary handlers
    with TemporaryLogControl(controller, keep_active=["Leader"], 
                            silence_level="CRITICAL", 
                            temporary_handlers={"Follower": ["file"]}):
        # Leader keeps its level, others are silenced
        assert controller.get_logger_level("Leader") == logging.DEBUG
        assert controller.get_logger_level("Follower") == logging.CRITICAL
        assert controller.get_logger_level("Candidate") == logging.CRITICAL
        # Follower gets temporary handler
        assert controller.get_logger_handlers("Follower") == ["file"]
    
    # All should be restored
    assert controller.get_logger_level("Leader") == original_leader_level
    assert controller.get_logger_level("Follower") == original_follower_level
    assert controller.get_logger_level("Candidate") == original_candidate_level
    assert controller.get_logger_handlers("Follower") == ["stdout"]
    LogController.controller = saved_log_controller 

async def test_temporary_handler_control():
    """Test TemporaryHandlerControl context manager"""
    from raftengine.deck.log_control import LogController, TemporaryHandlerControl
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Set initial handlers
    controller.set_logger_handlers("Leader", ["stdout"])
    controller.set_logger_handlers("Follower", ["file"])
    
    original_leader_handlers = controller.get_logger_handlers("Leader")
    original_follower_handlers = controller.get_logger_handlers("Follower")
    
    # Test temporary handler changes
    handler_changes = {
        "Leader": ["file"],
        "Follower": ["stdout", "file"]
    }
    
    with TemporaryHandlerControl(controller, handler_changes):
        # Handlers should be temporarily changed
        assert controller.get_logger_handlers("Leader") == ["file"]
        assert controller.get_logger_handlers("Follower") == ["stdout", "file"]
    
    # After context, handlers should be restored
    assert controller.get_logger_handlers("Leader") == original_leader_handlers
    assert controller.get_logger_handlers("Follower") == original_follower_handlers
    LogController.controller = saved_log_controller 

async def test_convenience_functions():
    """Test convenience functions for creating context managers"""
    from raftengine.deck.log_control import create_temporary_log_control, create_temporary_handler_control
    import logging
    
    # Test create_temporary_log_control
    with create_temporary_log_control(keep_active=["Leader"], silence_level="ERROR") as temp_control:
        # Should have a LogController instance
        assert hasattr(temp_control, 'log_controller')
        assert temp_control.keep_active == ["Leader"]
        assert temp_control.silence_level == "ERROR"
    
    # Test create_temporary_handler_control
    handler_changes = {"Leader": ["file"]}
    with create_temporary_handler_control(handler_changes) as temp_handler:
        # Should have a LogController instance
        assert hasattr(temp_handler, 'log_controller')
        assert temp_handler.handler_changes == handler_changes

async def test_to_dict_config():
    """Test to_dict_config method"""
    from raftengine.deck.log_control import LogController
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Set some custom levels
    controller.set_logger_level("Leader", "DEBUG")
    controller.set_logger_level("Follower", "INFO")
    
    # Add a custom handler
    controller.add_handler("custom_handler", "file", "Custom handler", 
                          filename="custom.log", mode="w")
    controller.assign_handler_to_logger("Candidate", "custom_handler")
    
    # Generate dict config
    config = controller.to_dict_config()
    
    # Check structure
    assert "version" in config
    assert "disable_existing_loggers" in config
    assert "formatters" in config
    assert "handlers" in config
    assert "loggers" in config
    
    assert config["version"] == 1
    assert config["disable_existing_loggers"] == True
    
    # Check handlers
    assert "stdout" in config["handlers"]
    assert "file" in config["handlers"]
    assert "custom_handler" in config["handlers"]
    
    stdout_handler = config["handlers"]["stdout"]
    assert stdout_handler["class"] == "logging.StreamHandler"
    assert stdout_handler["stream"] == "ext://sys.stdout"
    
    custom_handler = config["handlers"]["custom_handler"]
    assert custom_handler["class"] == "logging.FileHandler"
    assert custom_handler["filename"] == "custom.log"
    assert custom_handler["mode"] == "w"
    
    # Check loggers
    assert "Leader" in config["loggers"]
    assert "Follower" in config["loggers"]
    assert "Candidate" in config["loggers"]
    
    leader_logger = config["loggers"]["Leader"]
    assert leader_logger["level"] == "DEBUG"  # Custom level
    assert leader_logger["handlers"] == ["stdout"]
    assert leader_logger["propagate"] == False
    
    follower_logger = config["loggers"]["Follower"]
    assert follower_logger["level"] == "INFO"  # Custom level
    
    candidate_logger = config["loggers"]["Candidate"]
    assert candidate_logger["level"] == "ERROR"  # Default level
    assert "custom_handler" in candidate_logger["handlers"]
    LogController.controller = saved_log_controller 

async def test_get_known_copies():
    """Test get_known_loggers and get_known_handlers return copies"""
    from raftengine.deck.log_control import LogController
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Get copies
    loggers_copy = controller.get_known_loggers()
    handlers_copy = controller.get_known_handlers()
    
    # Modify copies
    loggers_copy["TestLogger"] = "modified"
    handlers_copy["TestHandler"] = "modified"
    
    # Original should be unchanged
    assert "TestLogger" not in controller.known_loggers
    assert "TestHandler" not in controller.known_handlers
    
    # Should be different objects
    assert loggers_copy is not controller.known_loggers
    assert handlers_copy is not controller.known_handlers
    LogController.controller = saved_log_controller 

async def test_apply_config():
    """Test apply_config method"""
    from raftengine.deck.log_control import LogController
    import logging
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Set a custom level
    controller.set_logger_level("Leader", "DEBUG")
    
    # Apply config should configure the logging system
    controller.apply_config()
    
    # Check that the actual logging system is configured
    leader_logger = logging.getLogger("Leader")
    assert leader_logger.level == logging.DEBUG
    LogController.controller = saved_log_controller 

async def test_internal_set_logger_level_without_custom_flag():
    """Test internal _set_logger_level_without_custom_flag method"""
    from raftengine.deck.log_control import LogController
    import logging
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Set a custom level first
    controller.set_logger_level("Leader", "DEBUG")
    assert controller.known_loggers["Leader"].custom_level == "DEBUG"
    
    # Use internal method to change level without marking as custom
    controller._set_logger_level_without_custom_flag("Leader", "INFO")
    assert controller.get_logger_level("Leader") == logging.INFO
    # Should still have custom level flag from before
    assert controller.known_loggers["Leader"].custom_level == "DEBUG"
    
    # Test with unknown logger
    with pytest.raises(ValueError, match="Unknown logger"):
        controller._set_logger_level_without_custom_flag("UnknownLogger", "INFO")
    LogController.controller = saved_log_controller 

async def test_remove_handler_removes_from_loggers():
    """Test that removing a handler removes it from all loggers"""
    from raftengine.deck.log_control import LogController
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Add a custom handler
    controller.add_handler("test_handler", "stream", "Test handler")
    
    # Assign it to multiple loggers
    controller.assign_handler_to_logger("Leader", "test_handler")
    controller.assign_handler_to_logger("Follower", "test_handler")
    
    # Verify it's assigned
    assert "test_handler" in controller.get_logger_handlers("Leader")
    assert "test_handler" in controller.get_logger_handlers("Follower")
    
    # Remove the handler
    controller.remove_handler("test_handler")
    
    # Should be removed from all loggers
    assert "test_handler" not in controller.get_logger_handlers("Leader")
    assert "test_handler" not in controller.get_logger_handlers("Follower")
    assert "test_handler" not in controller.list_handlers()
    LogController.controller = saved_log_controller 

async def test_handler_deduplication():
    """Test that handlers are not duplicated when assigned multiple times"""
    from raftengine.deck.log_control import LogController
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Assign same handler multiple times
    controller.assign_handler_to_logger("Leader", "file")
    controller.assign_handler_to_logger("Leader", "file")
    controller.assign_handler_to_logger("Leader", "file")
    
    # Should only appear once
    handlers = controller.get_logger_handlers("Leader")
    assert handlers.count("file") == 1
    LogController.controller = saved_log_controller 

async def test_temporary_log_control_with_nonexistent_logger():
    """Test TemporaryLogControl with nonexistent logger in temporary_handlers"""
    from raftengine.deck.log_control import LogController, TemporaryLogControl
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Should not crash with nonexistent logger
    with TemporaryLogControl(controller, temporary_handlers={"NonExistentLogger": ["stdout"]}):
        pass  # Should complete without error
    LogController.controller = saved_log_controller 
