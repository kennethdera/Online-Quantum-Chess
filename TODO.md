# TODO: Fix Quantum Rules Bugs in Django Project

## Summary
The Django project's quantum chess implementation has bugs in the quantum rules compared to the reference Code/Quant.py. The main issues are in the `detangle()` and `measure()` methods.

## Bugs Identified

### 1. detangle() method - Wrong matching logic
- **File:** `quantum_chess/quantum/quant.py`
- **Issue:** Uses exact state matching (`if i == add:`) instead of prefix matching
- **Reference (Code/Quant.py):** Uses `if i.startswith(add):`
- **Impact:** When measuring/entanglement, quantum pieces are not properly detangled because states with longer identifiers are not removed

### 2. measure() method - Wrong entanglement matching
- **File:** `quantum_chess/quantum/quant.py`
- **Issue:** Uses exact state matching (`if final_state == self.ent[i][2]`) instead of prefix matching
- **Reference (Code/Quant.py):** Uses `if final_state.startswith(self.ent[i][2]):`
- **Impact:** Entangled pieces are not properly collapsed when measuring

### 3. Missing entangling updates in detangle
- **File:** `quantum_chess/quantum/quant.py`
- **Issue:** The detangle method doesn't update the entanglement list
- **Reference (Code/Quant.py):** Has commented code for handling nested entanglement
- **Impact:** After measurement, stale entanglement references remain

## Tasks

- [ ] 1. Fix `detangle()` method to use prefix matching (startswith)
- [ ] 2. Fix `measure()` method entanglement detection to use prefix matching
- [ ] 3. Test the quantum rules to ensure proper entanglement and measurement behavior
