


leader_election.all_yes_votes.with_pre_vote
-------------------------------------------

This feature branch is the logic that applies when an election is held and all the non-candidate nodes accept the
candidate's bid on the first round of voting. That means that the candidate's term is greater than the follower's
terms, and the candidates committed log record index is at least as high as any other node's value.

Thesis section 9.6 describes the PreVote extension to the basic election protocol, and why it is desirable. The goal
is to avoid unecessary disruption of the cluster when a node gets out of sync and tries to become leader, as, for example,
when it suffers a network partition that is longer than the election timeout.

The general idea is that a candidate node sends out vote requests and the other nodes respond as they would to an actual vote,
but they do not increase their local term value. This works best for the intended goal when the voting node rejects
the PreVote when it has been in contact with the leader within less time than the election timeout.

This library uses this extension by default, but allows it to be disabled in the cluster config so only some tests
use this feature. It is often disabled for testing because it simplifies test development.

