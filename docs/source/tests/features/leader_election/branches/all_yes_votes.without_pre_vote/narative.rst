:orphan:

leader_election.all_yes_votes.without_pre_vote
----------------------------------------------

The election is held with voting, but without the PreVote
extension. This is the original protocol's election mechanism, without
the later PreVote extension. Most of the tests use this form of
election because it is easier to manipulate for setting up the
conditions of cluster state required for the particular test logic
since there are fewer steps and less variability.

