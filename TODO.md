# TODO: Fix Quantum Rules Bugs in Django Project

## Summary
The Django project's quantum chess implementation has bugs in the quantum rules compared to the reference Code/Quant.py and the Game Rule/Move Declaration Rule.txt.

## Bugs Identified and Fixed

### 1. detangle() method - Wrong matching logic
- **File:** `quantum_chess/quantum/quant.py`
- **Issue:** Used exact state matching instead of prefix matching
- **Fix:** Changed to prefix matching `if i.startswith(add):`

### 2. measure() method - Wrong entanglement matching
- **File:** `quantum_chess/quantum/quant.py`
- **Issue:** Used exact state matching instead of prefix matching
- **Fix:** Changed to prefix matching `if final_state.startswith(self.ent[i][2]):`

### 3. quantum_split() - Too restrictive validation
- **File:** `quantum_chess/views.py`
- **Issue:** Required target squares to be in legal moves AND empty, even in quantum mode
- **Fix:** In quantum mode, allows any two different empty squares

## Game Rule Refinement - Move Declaration Rule Implemented

Based on Game Rule/Move Declaration Rule.txt, the following refinements were implemented:

### 1. Move Commitment Principle
- Move type is now declared BEFORE any measurement occurs
- `declared_move_type` is set at the start of make_move
- This is locked - the move cannot change type after measurement

### 2. Classical Move Declaration
- Non-capturing moves cannot become captures after measurement
- If target square ends up occupied after measurement, move fails

### 3. Capture Move Declaration  
- Capture moves stay as captures - cannot become non-captures
- If defender collapses to different square, capture fails

### 4. Failed Move Consequence
- If declared move becomes invalid after measurement:
  - Moving piece stays on original square
  - Turn ends
  - Collapsed board state remains

### 5. No Retroactive Move Conversion
- Cannot change from capture to non-capture
- Cannot change from non-capture to capture
- Cannot change target squares after measurement

## Tasks Completed

- [x] Fix detangle() method to use prefix matching
- [x] Fix measure() method entanglement detection
- [x] Fix quantum_split validation
- [x] Implement Move Declaration Rule:
  - [x] Move type declared BEFORE measurement
  - [x] Classical moves stay non-captures
  - [x] Captures stay captures
  - [x] Failed moves leave piece on original square

## Files Modified
- quantum_chess/quantum/quant.py - Fixed detangle() and measure() methods
- quantum_chess/views.py - Implemented Move Declaration Rule and fixed quantum_split
