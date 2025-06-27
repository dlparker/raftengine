# Readable PlantUML Message Formatters Plan

## Problem Statement

The current PlantUML sequence diagrams generated from Raft test traces use heavily abbreviated message formats designed for table compression. This makes the diagrams difficult to understand without extensive legend knowledge.

**Current Issues:**
- Messages show cryptic shorthand like `poll t-1 li-0 lt-1` 
- Parameters are abbreviated (t=term, li=last_index, lt=last_term, etc.)
- Requires legend to understand abbreviations
- Dense, hard to read without domain knowledge

**Current Example:**
```
n1 -> n2: poll t-1 li-0 lt-1
n2 -> n1: vote yes-True
```

**Desired Readable Example:**
```
n1 -> n2: RequestVote(term=1, lastIndex=0, lastTerm=1)
n2 -> n1: VoteResponse(granted=True)
```

## Solution Plan

### 1. Create New Readable Message Formatters

**File**: `dev_tools/puml_message_formatters.py`

Create readable versions of each message formatter class:

- `RequestVoteReadableFormat`: `poll t-1 li-0 lt-1` → `RequestVote(term=1, lastIndex=0, lastTerm=1)`
- `VoteResponseReadableFormat`: `vote yes-True` → `VoteResponse(granted=True)`
- `AppendEntriesReadableFormat`: `ae t-1 i-0 lt-0 e-1 c-0` → `AppendEntries(term=1, prevIndex=0, prevTerm=0, entries=1, commitIndex=0)`
- `AppendResponseReadableFormat`: `ae_reply ok-True mi-1` → `AppendResponse(success=True, maxIndex=1)`
- `PreVoteReadableFormat`: `p_v_r t-1 li-0 lt-1` → `PreVoteRequest(term=1, lastIndex=0, lastTerm=1)`
- `PreVoteResponseReadableFormat`: `p_v yes-True` → `PreVoteResponse(granted=True)`
- `MembershipChangeReadableFormat`: `m_c op-add n-uri` → `MembershipChange(operation=add, node=uri)`
- `MembershipChangeResponseReadableFormat`: `m_cr op-add n-uri ok-True` → `MembershipChangeResponse(operation=add, node=uri, success=True)`
- `TransferPowerReadableFormat`: `t_p i-1` → `TransferPower(prevIndex=1)`
- `TransferPowerResponseReadableFormat`: `t_pr i-1 ok-True` → `TransferPowerResponse(prevIndex=1, success=True)`
- `SnapshotReadableFormat`: `sn i-1` → `Snapshot(prevIndex=1)`
- `SnapshotResponseReadableFormat`: `snr i-1 s-True` → `SnapshotResponse(prevIndex=1, success=True)`

### 2. Create Enhanced PUMLFormatter

**Enhancement**: Add `ReadablePUMLFormatter` class to `dev_tools/trace_formatters.py`

Key improvements:
- Use the new readable message formatters instead of shortest format
- Keep the same sequence diagram structure but with descriptive messages
- Add contextual annotations (e.g., "Election begins", "Quorum achieved")
- **Message clarity**: Full parameter names instead of abbreviations
- **Role transitions**: "Becomes CANDIDATE" instead of "NEW ROLE (CANDIDATE)"  
- **State changes**: "Log updated: index=1, term=1" instead of "li-1 lt-1"
- **Reduced legend dependency**: Self-explanatory messages

### 3. Integration & Testing

- Test with existing trace files to ensure proper output
- Add command-line option to choose between compact vs readable PlantUML output
- Maintain backward compatibility with existing PUMLFormatter
- Update any scripts that generate PlantUML files to offer readable option

## Expected Benefits

1. **Self-explanatory diagrams**: No need to constantly reference legend
2. **Accessibility**: Developers unfamiliar with Raft internals can understand the flow
3. **Better debugging**: Clear message content makes it easier to identify issues
4. **Documentation quality**: Diagrams can be used in documentation without extensive explanation

## Implementation Notes

- The readable formatters will be separate from the existing shortest formatters
- Existing table formatters (OrgFormatter, RstFormatter) will continue to use shortest format for space efficiency
- PlantUML has more space available, so we can afford descriptive text
- Backward compatibility maintained through separate formatter classes

## Files Modified/Created

1. **Created**: `dev_tools/puml_message_formatters.py` - New readable message formatters
2. **Modified**: `dev_tools/trace_formatters.py` - Add ReadablePUMLFormatter class
3. **Tested with**: Existing PlantUML files in `captures/test_traces/plantuml/`