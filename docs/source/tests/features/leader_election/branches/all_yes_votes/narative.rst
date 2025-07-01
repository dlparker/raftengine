leader_election.all_yes_votes
-----------------------------

This feature branch is the logic that applies when an election is held and all the non-candidate nodes accept the
candidate's bid on the first round of voting. That means that the candidate's term is greater than the follower's
terms, and the candidates committed log record index is at least as high as any other node's value.

