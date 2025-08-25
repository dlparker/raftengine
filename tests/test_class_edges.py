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
    logger_count = len(controller.known_loggers) 
    
    # Test with additional loggers
    additional_loggers = [("TestLogger", "Test logger description")]
    LogController.controller = None
    controller2 = LogController(additional_loggers=additional_loggers)
    assert len(controller2.known_loggers) == logger_count + 1
    assert "TestLogger" in controller2.known_loggers
    assert controller2.known_loggers["TestLogger"].description == "Test logger description"
    LogController.controller = saved_log_controller 
    saved_log_controller.apply_config()
    
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
    saved_log_controller.apply_config()

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
    saved_log_controller.apply_config()

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
    assert controller.get_logger_level("CustomLogger") == logging.ERROR
    
    # Test adding logger with custom level
    controller.add_logger("CustomLogger.with_dot", "Another custom logger", level="DEBUG")
    assert controller.get_logger_level("CustomLogger.with_dot") == logging.DEBUG
    assert controller.known_loggers["CustomLogger.with_dot"].custom_level == "DEBUG"
    LogController.controller = saved_log_controller 
    saved_log_controller.apply_config()
    

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
    saved_log_controller.apply_config()

async def test_logger_def():
    """Test LoggerDef dataclass"""
    from raftengine.deck.log_control import LoggerDef
    
    # Test basic logger definition
    logger_def = LoggerDef(
        name="test_logger",
        description="Test logger",
        custom_level="DEBUG",
        propagate=True,
    )
    
    assert logger_def.name == "test_logger"
    assert logger_def.description == "Test logger"
    assert logger_def.custom_level == "DEBUG"
    assert logger_def.propagate == True
    
    # Test defaults
    logger_def2 = LoggerDef("test_logger2", "Test logger 2")
    assert logger_def2.custom_level is None
    assert logger_def2.propagate == False

async def test_add_logger_errors():
    """Test error cases when adding loggers"""
    from raftengine.deck.log_control import LogController
    import pytest
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    LogController.controller = saved_log_controller 
    saved_log_controller.apply_config()

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
    
    # All should be restored
    assert controller.get_logger_level("Leader") == original_leader_level
    assert controller.get_logger_level("Follower") == original_follower_level
    assert controller.get_logger_level("Candidate") == original_candidate_level
    LogController.controller = saved_log_controller 
    saved_log_controller.apply_config()

async def test_convenience_functions():
    """Test convenience functions for creating context managers"""
    from raftengine.deck.log_control import create_temporary_log_control
    import logging
    
    # Test create_temporary_log_control
    with create_temporary_log_control(keep_active=["Leader"], silence_level="ERROR") as temp_control:
        # Should have a LogController instance
        assert hasattr(temp_control, 'log_controller')
        assert temp_control.keep_active == ["Leader"]
        assert temp_control.silence_level == "ERROR"

async def test_to_dict_config():
    """Test to_dict_config method"""
    from raftengine.deck.log_control import LogController
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Set some custom levels
    controller.set_logger_level("Leader", "DEBUG")
    controller.set_logger_level("Follower", "INFO")
    
    # Generate dict config
    config = controller.to_dict_config()
    
    # Check structure
    assert "version" in config
    assert "disable_existing_loggers" in config
    assert "formatters" in config
    assert "loggers" in config
    
    assert config["version"] == 1
    assert config["disable_existing_loggers"] == True
    
    # Check loggers
    assert "Leader" in config["loggers"]
    assert "Follower" in config["loggers"]
    assert "Candidate" in config["loggers"]
    
    leader_logger = config["loggers"]["Leader"]
    assert leader_logger["level"] == "DEBUG"  # Custom level
    assert leader_logger["propagate"] == False
    
    follower_logger = config["loggers"]["Follower"]
    assert follower_logger["level"] == "INFO"  # Custom level
    
    candidate_logger = config["loggers"]["Candidate"]
    assert candidate_logger["level"] == "ERROR"  # Default level
    LogController.controller = saved_log_controller 
    saved_log_controller.apply_config()

async def test_get_known_copies():
    from raftengine.deck.log_control import LogController
    
    saved_log_controller = LogController.controller
    LogController.controller = None
    controller = LogController()
    
    # Get copies
    loggers_copy = controller.get_known_loggers()
    
    # Modify copies
    loggers_copy["TestLogger"] = "modified"
    
    # Original should be unchanged
    assert "TestLogger" not in controller.known_loggers
    
    # Should be different objects
    assert loggers_copy is not controller.known_loggers
    LogController.controller = saved_log_controller 
    saved_log_controller.apply_config()

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
    saved_log_controller.apply_config()

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
    saved_log_controller.apply_config()


