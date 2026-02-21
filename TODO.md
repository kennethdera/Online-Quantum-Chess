# Quantum Split Capture Bug Fix

## Task
Fix the bug where fen is not being updated after quantum split and split pieces cannot be captured.

## Bug Analysis
The bug is in `quantum_chess/views.py` in the `make_move` function:
1. List indices become invalid after removing pieces from the quantum pieces list
2. Processing order causes index shifting issues
3. target_has_quantum check doesn't use the updated quantum pieces

## Fix Plan
- [x] Modify the quantum capture logic to use position names instead of list indices
- [x] Process the moving piece FIRST before any removals to avoid index shifting
- [x] Fix the target_has_quantum check to use the correct quantum pieces
