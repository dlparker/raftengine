# NodeStateShortestFormat Upgrade Plan

## Goal Understanding
Upgrade `NodeStateShortestFormat` to better match the legacy Shorthand system's formatting while preparing for future table generation flexibility.

## Current State Analysis

### NodeStateFormat.prep_format() produces:
```python
{
  "role": "FOLLOWER",           # Full role name
  "op": "message_formatted",    # Already correctly formatted by message formatters
  "delta": {                    # Raw field changes with full field names
    "last_index": 1,
    "last_term": 1, 
    "term": 1,
    "commit_index": 0,
    "leader_id": "mcpy://1"
  }
}
```

### Legacy Shorthand.shorten_node_states() produces:
- **Role**: Shortened (`FLWR`, `CNDI`, `LEAD`)
- **Op**: Already correctly handled by our message formatters
- **Delta**: Formatted list `[d_t, d_lt, d_li, d_ci, d_net]` converted to space-separated string

## Required Changes

### 1. Role Field Transformation
Transform `role` from full name to shortened form:
- `"FOLLOWER"` → `"FLWR"`
- `"CANDIDATE"` → `"CNDI"`  
- `"LEADER"` → `"LEAD"`

### 2. Delta Field Transformation
Transform `delta` from current key-value format to legacy-style dictionary format.

**Current delta format:**
```python
{"last_index": 1, "last_term": 1, "term": 1, "commit_index": 0, "leader_id": "mcpy://1"}
```

**Target delta format:**
```python
{
  "term": "t-1",              # from d_t = shtype.shorten_term(ns)
  "log_last_term": "lt-1",    # from d_lt = shtype.shorten_rec_term(ns)  
  "last_index": "li-1",       # from d_li = shtype.shorten_rec_index(ns)
  "commit_index": "ci-1",     # from d_ci = shtype.shorten_commit_index(ns)
  "network_id": "n=1"         # from d_net = shtype.shorten_net_id(nid)
}
```

### 3. Delta Logic Replication
Replicate the exact delta detection logic from `Shorthand.shorten_node_states()`:
- Only include fields that actually changed between current and previous state
- Handle network partition logic (`ns.on_quorum_net`)
- Handle special case for `PARTITION_HEALED` at position 0
- Use exact same shortening functions as `ShorthandType1`

## Implementation Plan

### Phase 1: Understand Legacy Logic
- [ ] **Task 1**: Analyze how `Shorthand.shorten_node_states()` builds the delta list
- [ ] **Task 2**: Map the delta detection logic to new format requirements
- [ ] **Task 3**: Identify all edge cases (partition healing, network states, etc.)

### Phase 2: Implement Role Shortening
- [ ] **Task 4**: Create `shorten_role()` method in `NodeStateShortestFormat`
- [ ] **Task 5**: Update `prep_format()` to use shortened role names

### Phase 3: Implement Delta Transformation  
- [ ] **Task 6**: Create delta detection logic that mirrors `shorten_node_states()`
- [ ] **Task 7**: Build dictionary with keys: `term`, `log_last_term`, `last_index`, `commit_index`, `network_id`
- [ ] **Task 8**: Use `ShorthandType1` static methods for value formatting
- [ ] **Task 9**: Handle network partition states and special cases

### Phase 4: Testing and Validation
- [ ] **Task 10**: Test against existing .org files to ensure delta fields match
- [ ] **Task 11**: Verify role shortening works correctly
- [ ] **Task 12**: Test edge cases (partitions, first entries, etc.)

## Questions for Clarification

1. **Dictionary Key Names**: You specified the target dictionary keys as `{term, log_last_term, last_index, commit_index, network_id}`. Is this mapping correct:
   - `d_t` (term changes) → `"term": "t-1"`
   - `d_lt` (log record term) → `"log_last_term": "lt-1"` 
   - `d_li` (log record index) → `"last_index": "li-1"`
   - `d_ci` (commit index) → `"commit_index": "ci-1"`
   - `d_net` (network state) → `"network_id": "n=1"`

2. **Empty Values**: In the legacy system, empty delta values (`""`) are filtered out by `format_log_list()`. Should empty values be:
   - Excluded from the dictionary entirely?
   - Included with empty string values?

3. **Network State Logic**: The network logic is complex in the legacy code. Should I replicate it exactly, including the `ns.on_quorum_net` checks and partition healing special cases?

4. **Future Compatibility**: Since you mentioned eventual table generation (.org, .rst, .puml), should I structure this to make that transition easier?

## Expected Output Format

After implementation, `NodeStateShortestFormat.prep_format()` should return:
```python
{
  "role": "FLWR",                     # Shortened role
  "op": "N-2+ae_reply ok-True mi-1",  # Already correctly formatted
  "delta": {                          # New structured delta format
    "term": "t-1",
    "last_index": "li-1", 
    "commit_index": "ci-1"
    # Only fields that actually changed
  }
}
```

Does this plan accurately capture your requirements?