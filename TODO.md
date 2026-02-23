# Implementation TODO - Quantum Chess Measurement Rules

## Task Summary
Implement measurement rules where measuring happens only when a piece is capturing or being captured.

## Rules to Implement:
1. Measurement can ONLY happen when:
   - A piece is CAPTURING another piece
   - A piece is BEING CAPTURED by another piece

2. If quantum piece is being captured:
   - Resolve which instance is the right position
   - If the captured piece IS the right one: remove other instances, let opponent capture
   - If the captured piece is NOT the right one: return opponent piece to original square, remove false positions, turn right position to classical piece

## Implementation Steps:

### Step 1: Update quantum_chess/quantum/quant.py
- [x] Modify `should_trigger_measurement()` to check if move is a capture
- [x] Add `should_trigger_measurement_on_being_captured()` method
- [x] Add `resolve_capture_measurement()` method for handling capture scenarios

### Step 2: Update quantum_chess/views.py
- [x] Update make_move to handle measurement outcomes based on capture rules
- [x] Add logic for when captured piece IS the right one vs NOT the right one

### Step 3: Test the implementation
- [ ] Verify measurements only trigger on captures
- [ ] Verify "right piece" case: remove other instances, allow capture
- [ ] Verify "wrong piece" case: return opponent to original, make right position classical
