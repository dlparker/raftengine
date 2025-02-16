from enum import Enum
    
class StateCode(str, Enum):

    """ Follower state, as defined in raftengine protocol """
    follower = "FOLLOWER"

    """ Candidate state, as defined in raftengine protocol """
    candidate = "CANDIDATE"

    """ Leader state, as defined in raftengine protocol """
    leader = "LEADER"

    def __str__(self):
        return self.value
    
class SubstateCode(str, Enum):
    # --- Expect from any state
    """ Before any connections """
    starting = "STARTING"

    """ newer term received """
    newer_term = "NEWER_TERM"

    """ older term received """
    older_term = "OLDER_TERM"

    # --- end expect from any state

    # --- Expect from Follower states
    """ Follower has not yet received leader contact """
    leader_unknown = "LEADER_UNKOWN"

    """ Follower has not received timely leader contact """
    leader_lost = "LEADER_LOST"

    """ received vote request, examining """
    planning_vote = "PLANNING_VOTE"

    """ cast vote """
    voting_yes = "VOTING_YES"

    """ cast vote """
    voting_no = "VOTING_NO"

    """ Follower, leader has called us at least once """
    joined_leader = "JOINED_LEADER"                  

    """ As of current call from leader, log is in sync """
    synced = "SYNCED"                 

    """ Leader log is newer than ours, requesting catchup """
    need_catchup = "NEED_CATCHUP"

    """ Leader log is newer than ours, processing append message"""
    appending = "APPENDING"

    """ Running command sent from leader """
    running_command = "RUNNING_COMMAND"

    """ Running command sent from leader succeeded """
    command_done = "COMMAND_DONE"

    """ Running command sent from leader caused an error """
    command_error = "COMMAND_ERROR"

    """ Logged result of successfully running command """
    logged_command = "LOGGED_COMMAND"

    """ Sent leader result of running command """
    replied_to_command = "REPLIED_TO_COMMAND"

    """ LAST call from leader synced new records """
    synced_prepare = "SYNCED_RECORDS"
    # --- end expect from Follower states

    # --- Expect from Candidate states
    """ Candidate starting election """
    start_election = "START_ELECTION"

    """ no votes in yet """
    no_votes_in = "NO_VOTES_IN"

    """ at least one vote in """
    some_votes_in = "SOME_VOTES_IN"

    """ enough votes in, election won """
    won = "WON"

    """ enough votes in, election lost """
    lost = "LOST"
    # --- end expect from Candidate states

    # --- Expect from Leader states
    """ Just got elected, no broadcasts yet"""
    elected = "ELECTED"
    
    """ Just broadcast heartbeats """
    sent_heartbeat = "SENT_HEARTBEAT"
    
    """ At least some hearbeat responses in """
    some_heartbeats_in = "SOME_HEARTBEATS_IN"
    
    """ All expected hearbeat responses in """
    all_heartbeats_in = "ALL_HEARTBEATS_IN"
    
    """ Just sent new log entries append (as leader) """
    sent_new_entries = "SENT_NEW_ENTRIES"

    """ Running and saving command after committed by peers """
    committing_command = "COMMITTING_COMMAND"

    # --- end expect from Leader states

    
    def __str__(self):
        return self.value
