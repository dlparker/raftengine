# NewOrgFormatter Implementation Plan

## Goal
Create a `NewOrgFormatter` that replicates `OrgFormatter` output but uses `NodeStateShortestFormat` instead of the legacy `Shorthand` system.

## Key Changes Required

### 1. Update NodeStateShortestFormat.format()
- **Current**: Returns JSON string `json.dumps(data)`
- **New**: Return the data dictionary directly
- **Breaking Change**: Will break our test scripts that expect JSON strings

### 2. Create NewOrgFormatter Class
Replace `trace_output.make_shorthand_table()` with new logic that:
- Uses `NodeStateShortestFormat` instead of `Shorthand`
- Maintains same table structure (Role | Op | Delta per node)
- Preserves exact formatting and spacing

### 3. Update Test Scripts
Fix the following files that depend on JSON string output:
- `test_message_formatters.py`
- `test_format_comparison.py` 
- `test_nodestate_upgrade.py`
- `new_format_tool.py`

## Implementation Details

### NodeStateShortestFormat Changes
```python
def format(self):
    # OLD: return json.dumps(data)
    # NEW: return data directly
    return self.prep_format()

# Optional: Add backwards compatibility method
def format_json(self):
    return json.dumps(self.format())
```

### NewOrgFormatter Structure
```python
class NewOrgFormatter:
    def __init__(self, trace_output):
        self.trace_output = trace_output
    
    def format(self, include_legend=True):
        # Replicate OrgFormatter.format() exactly but use NodeStateShortestFormat
        
    def make_new_shorthand_table(self, section):
        # Replace trace_output.make_shorthand_table() logic
        # Use NodeStateShortestFormat instead of Shorthand
```

### Table Generation Logic
1. **Get filtered events** (same as legacy)
2. **For each trace line**:
   - Track state history per node
   - Create `NodeStateShortestFormat(node_state, prev_state)`
   - Extract `role`, `op`, `delta` from returned dictionary
3. **Build table rows** with same 3-column structure
4. **Format with same headers and spacing**

### Delta Value Extraction
Legacy format: `"t-1 lt-1 li-1 ci-1"`
New format: `{"term": "t-1", "log_last_term": "lt-1", "last_index": "li-1", "commit_index": "ci-1", "network_id": ""}`

Convert new format to legacy string:
```python
def format_delta_string(delta_dict):
    items = [v for v in delta_dict.values() if v != ""]
    return " ".join(items)
```

## Implementation Steps

### Phase 1: Update NodeStateShortestFormat
- [ ] Change `format()` to return dict instead of JSON string
- [ ] Add `format_json()` method for backwards compatibility

### Phase 2: Fix Test Scripts
- [ ] Update `test_message_formatters.py` to use new format
- [ ] Update `test_format_comparison.py` to use new format  
- [ ] Update `test_nodestate_upgrade.py` to use new format
- [ ] Update `new_format_tool.py` to use new format

### Phase 3: Implement NewOrgFormatter
- [ ] Create `NewOrgFormatter` class
- [ ] Implement `make_new_shorthand_table()` method
- [ ] Replicate table generation with same structure
- [ ] Handle column widths and spacing

### Phase 4: Testing and Validation
- [ ] Test against existing .org files
- [ ] Ensure identical output to legacy OrgFormatter
- [ ] Verify all message types work correctly

## Expected Benefits
- **Cleaner architecture**: No more legacy Shorthand dependencies
- **Better maintainability**: All formatting logic centralized in NodeStateShortestFormat
- **Future flexibility**: Easy to extend for .rst and .puml formatters
- **Same output**: Exact compatibility with existing .org files

## Compatibility Notes
- All existing .org files should remain identical
- All table structure and spacing preserved
- All message formatting maintained through our new formatters
- Only internal implementation changes - no user-visible differences