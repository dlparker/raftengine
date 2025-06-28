.. leader_election.all_yes_votes.without_pre_vote:

Leader election -> All nodes vote yes: without PreVote extension
==============================================================

Thesis references
-----------------
* **Leader election**: section 3.4
* **Election restrictions**: section 3.6


This feature branch is the logic that applies when an election is held and all the non-candidate nodes accept the
candidate's bid on the first round of voting. That means that the candidate's term is greater than the follower's
terms, and the candidates committed log record index is at least as high as any other node's value.

This is the original protocol's election mechanism, without the later PreVote extension. Most of the tests
use this form of election because it is easier to manipulate for setting up the conditions of cluster state
required for the particular test logic since there are fewer steps and less variability. 

