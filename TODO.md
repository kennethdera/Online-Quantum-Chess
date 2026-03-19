# Quantum Chess Capture Rules Implementation - COMPLETED

## Task Summary
Implemented measurement game rule update for when a quantum piece attempts to capture another quantum piece.

## Three Capture Instances Implemented:

### Instance 1: Real Attacker + Real Defender
- Both pieces exist at their respective squares
- Remove fake pieces of both
- Attacker captures defender
- Attacker piece changes to classical piece

### Instance 2: Real Attacker + Fake Defender
- Attacker is at from_square, but defender is NOT at to_square
- Remove fake instances of both defender and attacker
- Attacker remains in original square (capture fails)

### Instance 3: Fake Attacker + Fake Defender
- Neither piece exists at the attempted squares
- Fake pieces are removed from board
- Attacker remains on original square (capture fails)

## Implementation Complete:

- [x] 1. Add resolve_quantum_vs_quantum_capture method in quant.py
- [x] 2. Fix indentation issues in quant.py
- [x] 3. Update views.py to use new method when both squares have quantum pieces

## Files Modified:
1. quantum_chess/quantum/quant.py - Added new method resolve_quantum_vs_quantum_capture
2. quantum_chess/views.py - Updated to use the new unified method for quantum vs quantum captures
