"""
Quantum Chess Logic using Qiskit

This module contains the quantum computing logic for quantum chess,
adapted from the original Code/Quant.py to work with Django.
"""

import math
import random
from typing import Dict, List, Tuple, Optional, Any

# Try to import qiskit, but provide fallback if not available
try:
    import qiskit
    from qiskit import QuantumCircuit, ClassicalRegister, QuantumRegister
    from qiskit import Aer, execute
    QISKIT_AVAILABLE = True
except ImportError:
    QISKIT_AVAILABLE = False
    # Mock classes for when qiskit is not available
    class QuantumCircuit:
        pass
    class QuantumRegister:
        pass
    class ClassicalRegister:
        pass

# Get backend - use simulator if qiskit is available
if QISKIT_AVAILABLE:
    try:
        backend = Aer.get_backend('qasm_simulator')
    except:
        backend = None
else:
    backend = None


class QuantumPiece:
    """
    Represents a quantum chess piece that can be in superposition.
    """
    
    def __init__(self, position: str, piece: Any):
        """
        Initialize a quantum piece.
        
        Args:
            position: Chess square position (e.g., 'a1', 'e4')
            piece: The chess piece object
        """
        self.piece = piece
        # qnum format: {state_id: [position, probability]}
        # Initial state: position with probability 1
        self.qnum = {'0': [position, 1]}
        self.ent = []  # Entanglement list
    
    def split(self, i_add: str, pos1: str, pos2: str) -> None:
        """
        Split a quantum piece into two positions (superposition).
        
        Args:
            i_add: The state identifier to split
            pos1: First position in superposition
            pos2: Second position in superposition
        """
        # The piece at position i_add gets split into two pieces
        # Each with half the probability of the original
        self.qnum[i_add + '0'] = ["", 0]
        self.qnum[i_add + '1'] = ["", 0]
        self.qnum[i_add + '0'][0] = pos1
        self.qnum[i_add + '1'][0] = pos2
        self.qnum[i_add + '0'][1] = self.qnum[i_add][1] / 2.0
        self.qnum[i_add + '1'][1] = self.qnum[i_add][1] / 2.0
        del self.qnum[i_add]
    
    def entangle_oneblock(self, i_add: str, pos1: str, obj: 'QuantumPiece', obj_add: str) -> None:
        """
        Entangle this piece with another piece when moving through a blocked position.
        
        Args:
            i_add: State identifier for this piece
            pos1: Target position
            obj: The blocking quantum piece
            obj_add: State identifier of the blocking piece
        """
        # When a piece moves and another piece is blocking the path,
        # the two pieces become entangled
        
        prob_blocked_piece = self.qnum[i_add][1]
        prob_blocking_piece = obj.qnum[obj_add][1]
        
        x = prob_blocked_piece
        y = prob_blocking_piece
        
        # Calculate probabilities after entanglement
        a = x * y  # prob_not_moved = prob_blocked * prob_blocking
        b = x * (1 - y)  # prob_moved = prob_blocked_piece * (1 - prob_blocking_piece)
        
        self.qnum[i_add + '0'] = ["", 0]
        self.qnum[i_add + '1'] = ["", 0]
        self.qnum[i_add + '0'][0] = self.qnum[i_add][0]
        self.qnum[i_add + '1'][0] = pos1
        self.qnum[i_add + '0'][1] = a
        self.qnum[i_add + '1'][1] = b
        del self.qnum[i_add]
        
        # Calculate the complementary state for the other piece
        last_state = obj_add[:-1] + str(int(not(int(obj_add[-1]))))
        
        # Add entanglement relationships
        obj.ent += [(self, i_add + '1', obj_add), (self, i_add + '0', last_state)]
        self.ent += [(obj, obj_add, i_add + '1'), (obj, last_state, i_add + '0')]
    
    def entangle_twoblock(self, i_add: str, pos1: str, pos2: str, 
                          obj1: 'QuantumPiece', obj1_add: str, 
                          obj2: 'QuantumPiece', obj2_add: str) -> None:
        """
        Entangle this piece with two blocking pieces.
        
        Args:
            i_add: State identifier for this piece
            pos1: First target position
            pos2: Second target position  
            obj1: First blocking piece
            obj1_add: State identifier of first blocking piece
            obj2: Second blocking piece
            obj2_add: State identifier of second blocking piece
        """
        prob_i_pos = self.qnum[i_add][1]
        prob_ob1 = obj1.qnum[obj1_add][1]
        prob_ob2 = obj2.qnum[obj2_add][1]
        
        if obj1 == obj2:
            # Both positions blocked by the same piece
            prob_pos1 = prob_i_pos * prob_ob2 + 0.5 * prob_i_pos * (1 - prob_ob1 - prob_ob2)
            prob_pos2 = prob_i_pos * prob_ob1 + 0.5 * prob_i_pos * (1 - prob_ob1 - prob_ob2)
            
            self.qnum[i_add + '0'] = ["", 0]
            self.qnum[i_add + '1'] = ["", 0]
            self.qnum[i_add + '0'][0] = pos1
            self.qnum[i_add + '0'][1] = prob_pos1
            self.qnum[i_add + '1'][0] = pos2
            self.qnum[i_add + '1'][1] = prob_pos2
            
            last_state1 = obj1_add[:-1] + str(int(not(int(obj1_add[-1]))))
            last_state2 = obj2_add[:-1] + str(int(not(int(obj2_add[-1]))))
            
            obj1.ent += [(self, i_add + '0', obj1_add), (self, i_add + '1', last_state1)]
            obj2.ent += [(self, i_add + '1', obj2_add), (self, i_add + '0', last_state2)]
            self.ent += [
                (obj1, obj1_add, i_add + '0'), (obj1, last_state1, i_add + '1'),
                (obj2, obj2_add, i_add + '1'), (obj2, last_state2, i_add + '0')
            ]
        else:
            # Two different blocking pieces
            prob_unmoved = prob_i_pos * prob_ob1 * prob_ob2
            prob_pos1 = prob_i_pos * (1 - prob_ob1) * prob_ob2 + 0.5 * prob_i_pos * (1 - prob_ob1) * (1 - prob_ob2)
            prob_pos2 = prob_i_pos * prob_ob1 * (1 - prob_ob2) + 0.5 * prob_i_pos * (1 - prob_ob1) * (1 - prob_ob2)
            
            self.qnum[i_add + '00'] = ["", 0]
            self.qnum[i_add + '01'] = ["", 0]
            self.qnum[i_add + '10'] = ["", 0]
            self.qnum[i_add + '00'][0] = self.qnum[i_add][0]
            self.qnum[i_add + '01'][0] = pos1
            self.qnum[i_add + '10'][0] = pos2
            self.qnum[i_add + '00'][1] = prob_unmoved
            self.qnum[i_add + '01'][1] = prob_pos1
            self.qnum[i_add + '10'][1] = prob_pos2
            
            last_state1 = obj1_add[:-1] + str(int(not(int(obj1_add[-1]))))
            last_state2 = obj2_add[:-1] + str(int(not(int(obj2_add[-1]))))
            
            obj1.ent += [(self, i_add + '01', obj1_add), (self, i_add + '00', last_state1)]
            obj2.ent += [(self, i_add + '10', obj2_add), (self, i_add + '00', last_state2)]
            self.ent += [
                (obj1, obj1_add, i_add + '01'), (obj1, last_state1, i_add + '00'),
                (obj2, obj2_add, i_add + '10'), (obj2, last_state2, i_add + '00')
            ]
        
        del self.qnum[i_add]
    
    def detangle(self, add: str, obj: 'QuantumPiece') -> None:
        """
        Remove entanglement when a piece is measured.
        
        Args:
            add: State identifier to remove
            obj: The piece this one was entangled with
        """
        probs = 0
        all_states = list(self.qnum.keys())
        for i in all_states:
            # Use exact state matching instead of prefix matching
            if i == add:
                del self.qnum[i]
            else:
                probs += self.qnum[i][1]
        
        # Normalize probabilities - add division by zero protection
        if probs > 0:
            for i in self.qnum:
                self.qnum[i][1] /= probs
    
    def measure(self) -> Tuple[str, float]:
        """
        Measure the quantum piece, collapsing the wavefunction.
        
        Returns:
            Tuple of (final_position, probability)
        """
        if not QISKIT_AVAILABLE or backend is None:
            # Classical simulation fallback
            return self._classical_measure()
        
        # Determine the quantum level (number of qubits needed)
        level = 0
        for i in self.qnum:
            if len(i) > level:
                level = len(i)
        
        if level == 0:
            # Single position, no superposition
            state = list(self.qnum.keys())[0]
            return self.qnum[state][0], self.qnum[state][1]
        
        # Build quantum circuit
        params = [0 + 0j] * (2 ** (level - 1))
        states = [bin(i)[2:].zfill(level - 1) for i in range(0, 2 ** (level - 1))]
        poss_states = list(self.qnum.keys())
        poss_states = [poss_states[i][1:] for i in range(0, len(poss_states))]
        
        for i in range(0, len(poss_states)):
            if len(poss_states[i]) < level:
                index = states.index(poss_states[i] + '0' * (level - 1 - len(poss_states[i])))
                params[index] = self.qnum['0' + poss_states[i]][1] ** 0.5 + 0j
        
        # Initialize quantum circuit
        qr = QuantumRegister(level - 1)
        cr = ClassicalRegister(level - 1)
        ckt = QuantumCircuit(qr, cr)
        ckt.initialize(params, [qr[i] for i in range(level - 1)])
        ckt.measure_all()
        
        # Execute
        job = execute(ckt, backend, shots=1)
        res = job.result()
        final_state = list(res.get_counts().keys())[0][:(level - 1)]
        
        # Find valid state
        while True:
            if final_state in poss_states:
                break
            final_state = final_state[:-1]
            if not final_state:
                break
        
        final_state = '0' + final_state
        
        # Detangle entangled pieces - use exact state matching
        for i in range(len(self.ent)):
            if final_state == self.ent[i][2]:
                self.ent[i][0].detangle(self.ent[i][1], self)
        
        # Set final position
        final_pos = self.qnum[final_state][0]
        self.qnum.clear()
        self.ent.clear()
        self.qnum['0'] = [final_pos, 1]
        
        return final_pos, 1.0
    
    def _classical_measure(self) -> Tuple[str, float]:
        """
        Classical measurement fallback when Qiskit is not available.
        """
        # Get all states and their probabilities
        states = list(self.qnum.keys())
        probabilities = [self.qnum[s][1] for s in states]
        
        # Normalize probabilities
        total = sum(probabilities)
        if total > 0:
            probabilities = [p / total for p in probabilities]
        
        # Choose based on probability
        rand = random.random()
        cumulative = 0
        for i, prob in enumerate(probabilities):
            cumulative += prob
            if rand <= cumulative:
                return self.qnum[states[i]][0], self.qnum[states[i]][1]
        
        # Fallback to first state
        return self.qnum[states[0]][0], self.qnum[states[0]][1]

    
    def to_dict(self) -> Dict:
        """
        Convert quantum piece to dictionary for JSON serialization.
        """
        return {
            'piece': str(self.piece) if self.piece else None,
            'qnum': self.qnum,
            'entangled': [
                {
                    'piece': str(ent[0].piece) if ent[0] else None,
                    'state': ent[1],
                    'related_state': ent[2]
                }
                for ent in self.ent
            ]
        }
    
    @classmethod
    def from_dict(cls, data: Dict, piece: Any) -> 'QuantumPiece':
        """
        Create quantum piece from dictionary.
        """
        qp = cls(data.get('position', 'a1'), piece)
        qp.qnum = data.get('qnum', {'0': [data.get('position', 'a1'), 1]})
        # Note: Entanglement needs to be reconstructed
        return qp


class QuantumGame:
    """
    Manages a quantum chess game.
    """
    
    def __init__(self):
        self.quantum_pieces: List[QuantumPiece] = []
        self.quantum_mode = False
        self.split_turn = False
    
    def add_quantum_piece(self, position: str, piece: Any) -> QuantumPiece:
        """
        Add a quantum piece to the game.
        """
        qp = QuantumPiece(position, piece)
        self.quantum_pieces.append(qp)
        return qp
    
    def find_quantum_piece_at(self, square: str) -> Optional[Tuple[QuantumPiece, str]]:
        """
        Find a quantum piece at a given square.
        """
        for qp in self.quantum_pieces:
            for state in qp.qnum.keys():
                if qp.qnum[state][0] == square:
                    return qp, state
        return None

    
    def get_all_positions(self) -> Dict[str, List[Tuple[Any, float]]]:
        """
        Get all positions and their probabilities.
        """
        positions = {}
        for qp in self.quantum_pieces:
            for state in qp.qnum.keys():
                pos = qp.qnum[state][0]
                prob = qp.qnum[state][1]
                if pos not in positions:
                    positions[pos] = []
                positions[pos].append((qp.piece, prob))
        return positions
    
    def measure_piece(self, square: str) -> Optional[Tuple[str, float]]:
        """
        Measure a quantum piece at a given square.
        """
        result = self.find_quantum_piece_at(square)
        if result:
            qp, state = result
            return qp.measure()
        return None
    
    def detect_conflicts(self) -> Dict[str, List[Tuple['QuantumPiece', str, float]]]:
        """
        Detect squares that have conflicts - squares occupied by different pieces
        in superposition (triggering measurement according to game rules).
        
        Returns:
            Dictionary mapping square names to list of (piece, state_id, probability)
        """
        # Get all positions and which pieces occupy them
        square_occupants: Dict[str, List[Tuple['QuantumPiece', str, float]]] = {}
        
        for qp in self.quantum_pieces:
            for state_id, state_data in qp.qnum.items():
                pos = state_data[0]
                prob = state_data[1]
                if pos not in square_occupants:
                    square_occupants[pos] = []
                square_occupants[pos].append((qp, state_id, prob))
        
        # Find conflicts: squares with multiple DIFFERENT pieces
        conflicts = {}
        for square, occupants in square_occupants.items():
            if len(occupants) > 1:
                # Check if they are different pieces (not just different states of same piece)
                different_pieces = []
                seen_pieces = set()
                for qp, state_id, prob in occupants:
                    piece_id = id(qp)
                    if piece_id not in seen_pieces:
                        seen_pieces.add(piece_id)
                        different_pieces.append((qp, state_id, prob))
                
                if len(different_pieces) > 1:
                    conflicts[square] = different_pieces
        
        return conflicts
    
    def should_trigger_measurement(self, from_square: str, to_square: str, 
                                   moving_piece_color: bool, is_capture: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if a move should trigger a measurement according to game rules.
        
        A measurement is triggered when:
        1. A piece is CAPTURING another piece (destination has a quantum piece in superposition)
        2. A piece is BEING CAPTURED (source had a quantum piece that's being captured)
        3. BOTH source and destination have quantum pieces - BOTH need to be measured!
        
        Args:
            from_square: Source square of the move
            to_square: Destination square of the move
            moving_piece_color: True for white, False for black
            is_capture: Whether this is a capture move
        
        Returns:
            Tuple of (should_measure, conflict_square, other_square)
            - conflict_square: the primary square to measure
            - other_square: the other square that also has a quantum piece (if any)
        """
        # Measurement can ONLY happen during a capture
        if not is_capture:
            return False, None, None
        
        # Check if the destination square has a quantum piece that could be captured
        dest_has_quantum = False
        for qp in self.quantum_pieces:
            for state_id, state_data in qp.qnum.items():
                if state_data[0] == to_square:
                    dest_has_quantum = True
                    break
            if dest_has_quantum:
                break
        
        # Check if the source square has a quantum piece (the attacker in superposition)
        source_has_quantum = False
        for qp in self.quantum_pieces:
            for state_id, state_data in qp.qnum.items():
                if state_data[0] == from_square:
                    source_has_quantum = True
                    break
            if source_has_quantum:
                break
        
        # BUG FIX: When BOTH squares have quantum pieces, BOTH need to be measured!
        # This happens when a quantum split piece attempts to capture another quantum piece
        if source_has_quantum and dest_has_quantum:
            # Both attacker and defender are quantum pieces
            # Need to measure both - return destination as primary, source as other
            return True, to_square, from_square
        
        # Check if the destination square has a quantum piece that could be captured
        # This is case: The moving piece is CAPTURING a quantum piece
        if dest_has_quantum:
            return True, to_square, None
        
        # Check if the source square has a quantum piece
        # This is case: The piece at source is being captured (by being moved away)
        if source_has_quantum:
            return True, from_square, None
        
        return False, None, None
    
    def should_trigger_measurement_on_being_captured(self, from_square: str, to_square: str,
                                                      moving_piece_color: bool) -> Tuple[bool, Optional[str]]:
        """
        Check if a quantum piece at from_square is being "captured" by the move.
        
        This happens when:
        - A quantum piece exists at from_square in superposition
        - Another piece (classical or quantum) also exists at from_square
        - This creates a conflict that needs measurement
        
        Args:
            from_square: Source square of the move
            to_square: Destination square of the move
            moving_piece_color: Color of the moving piece
        
        Returns:
            Tuple of (should_measure, conflict_square)
        """
        conflicts = self.detect_conflicts()
        
        # Check if source square has a conflict (multiple pieces there)
        if from_square in conflicts:
            return True, from_square
        
        return False, None
    
    def resolve_capture_measurement(self, capture_square: str, capturing_piece_color: bool,
                                    is_capturing: bool = True) -> Dict[str, any]:
        """
        Resolve measurement for a capture scenario according to game rules.
        
        Rules:
        - If quantum piece IS the right one: remove other instances, let opponent capture
        - If quantum piece is NOT the right one: return opponent piece to original square,
          remove false positions, turn right position to classical piece
        
        Args:
            capture_square: The square where capture is attempted
            capturing_piece_color: Color of the piece making the capture
            is_capturing: True if the quantum piece is being captured (moving piece captures it)
                          False if the moving piece IS the quantum piece being captured
        
        Returns:
            Dictionary with measurement results and action to take
        """
        # Find all quantum pieces at the capture square
        pieces_at_square = []
        for qp in self.quantum_pieces:
            for state_id, state_data in qp.qnum.items():
                if state_data[0] == capture_square:
                    pieces_at_square.append((qp, state_id, state_data[1]))
        
        if not pieces_at_square:
            return {'success': False, 'error': 'No quantum pieces at capture square'}
        
        # If there's only one piece at the square, measure it
        if len(pieces_at_square) == 1:
            qp, state_id, prob = pieces_at_square[0]
            
            # Randomly determine if piece exists at this square
            rand = random.random()
            piece_exists = rand < prob
            
            if piece_exists:
                # The piece IS at the capture square - "right one" case
                # Remove other instances, keep this one
                states_to_remove = [sid for sid in qp.qnum.keys() if sid != state_id]
                for sid in states_to_remove:
                    del qp.qnum[sid]
                
                # Set to 100% probability
                qp.qnum[state_id][1] = 1.0
                
                return {
                    'success': True,
                    'action': 'capture_succeeds',
                    'selected_piece': str(qp.piece),
                    'capture_square': capture_square,
                    'outcome': 'piece_exists_at_square'
                }
            else:
                # The piece is NOT at the capture square - "wrong one" case
                # Remove this state, keep other positions
                del qp.qnum[state_id]
                
                # Renormalize probabilities
                remaining_prob = sum(s[1] for s in qp.qnum.values())
                if remaining_prob > 0:
                    for s in qp.qnum.values():
                        s[1] /= remaining_prob
                
                # Turn the piece into a classical piece at the correct position
                # Find another position that has probability
                other_positions = [(sid, data) for sid, data in qp.qnum.items() if data[1] > 0]
                if other_positions:
                    # Keep only the first remaining position as classical
                    correct_state_id, correct_data = other_positions[0]
                    final_position = correct_data[0]
                    
                    # Remove all other states
                    states_to_remove = [sid for sid in qp.qnum.keys() if sid != correct_state_id]
                    for sid in states_to_remove:
                        del qp.qnum[sid]
                    
                    # Set to classical (100% probability)
                    qp.qnum = {correct_state_id: [final_position, 1.0]}
                    
                    return {
                        'success': True,
                        'action': 'capture_fails_make_classical',
                        'selected_piece': str(qp.piece),
                        'new_position': final_position,
                        'outcome': ''
                    }
                
                return {
                    'success': True,
                    'action': 'capture_fails_no_position',
                    'selected_piece': str(qp.piece),
                    'outcome': 'piece_does_not_exist'
                }
        
        # Multiple pieces at square - need to resolve which one is there
        # This is a conflict situation
        total_prob = sum(prob for _, _, prob in pieces_at_square)
        normalized_probs = [prob / total_prob for _, _, prob in pieces_at_square]
        
        rand = random.random()
        cumulative = 0
        selected_idx = 0
        
        for i, prob in enumerate(normalized_probs):
            cumulative += prob
            if rand <= cumulative:
                selected_idx = i
                break
        
        selected_qp, selected_state, selected_prob = pieces_at_square[selected_idx]
        
        # Collapse to the selected piece
        states_to_remove = [sid for sid in selected_qp.qnum.keys() if sid != selected_state]
        for sid in states_to_remove:
            del selected_qp.qnum[sid]
        selected_qp.qnum[selected_state][1] = 1.0
        
        return {
            'success': True,
            'action': 'capture_succeeds',
            'selected_piece': str(selected_qp.piece),
            'capture_square': capture_square,
            'outcome': 'piece_determined'
        }
    
    def resolve_measurement(self, conflict_square: str) -> Dict[str, any]:
        """
        Resolve a measurement at a conflict square following the minimal influence principle.
        Only resolves the specific conflict, leaving other superpositions untouched.
        
        Args:
            conflict_square: The square where measurement occurs
        
        Returns:
            Dictionary with measurement results
        """
        conflicts = self.detect_conflicts()
        
        if conflict_square not in conflicts:
            return {'success': False, 'error': 'No conflict at this square'}
        
        occupants = conflicts[conflict_square]
        measurement_results = []
        
        # Randomly select which piece occupies the square based on probabilities
        total_prob = sum(prob for _, _, prob in occupants)
        if total_prob == 0:
            return {'success': False, 'error': 'Zero total probability'}
        
        # Normalize probabilities
        normalized_probs = [prob / total_prob for _, _, prob in occupants]
        
        # Random selection
        rand = random.random()
        cumulative = 0
        selected_idx = 0
        
        for i, prob in enumerate(normalized_probs):
            cumulative += prob
            if rand <= cumulative:
                selected_idx = i
                break
        
        selected_qp, selected_state, selected_prob = occupants[selected_idx]
        
        # Collapse the selected piece to the conflict square
        # Remove other states of the selected piece (minimal influence on this piece)
        states_to_remove = []
        for state_id in list(selected_qp.qnum.keys()):
            if state_id != selected_state:
                states_to_remove.append(state_id)
        
        for state_id in states_to_remove:
            del selected_qp.qnum[state_id]
        
        # Set the selected state to 100% probability
        selected_qp.qnum[selected_state][1] = 1.0
        
        # For other pieces at this square, they are "not here" - collapse them elsewhere
        for i, (qp, state_id, prob) in enumerate(occupants):
            if i != selected_idx:
                # This piece is NOT at the conflict square
                # Remove this state from the piece
                if state_id in qp.qnum:
                    del qp.qnum[state_id]
                
                # Renormalize remaining probabilities
                remaining_prob = sum(s[1] for s in qp.qnum.values())
                if remaining_prob > 0:
                    for s in qp.qnum.values():
                        s[1] /= remaining_prob
        
        # Record measurement result
        measurement_results.append({
            'square': conflict_square,
            'selected_piece': str(selected_qp.piece),
            'probability': selected_prob,
            'outcome': 'exists_at_square' if selected_qp.qnum[selected_state][0] == conflict_square else 'not_at_square'
        })
        
        return {
            'success': True,
            'conflict_square': conflict_square,
            'results': measurement_results,
            'selected_piece': str(selected_qp.piece)
        }
    
    def check_schrodinger_capture(self, from_square: str, to_square: str,
                                   moving_piece_color: bool) -> Tuple[bool, Optional['QuantumPiece']]:
        """
        Check if a capture is a Schrödinger's cat scenario (no measurement needed).
        
        Schrödinger's cat: Capturing a superposed piece doesn't trigger measurement
        if the target square is only occupied by that one piece (no conflict).
        
        Args:
            from_square: Source square
            to_square: Target square (capture destination)
            moving_piece_color: Color of capturing piece
        
        Returns:
            Tuple of (is_schrodinger, captured_quantum_piece)
        """
        # Check if target square has a quantum piece
        target_occupant = None
        for qp in self.quantum_pieces:
            for state_id, state_data in qp.qnum.items():
                if state_data[0] == to_square:
                    target_occupant = qp
                    break
            if target_occupant:
                break
        
        if not target_occupant:
            return False, None  # No quantum piece to capture
        
        # Check if this is the ONLY piece at to_square (Schrödinger's cat scenario)
        conflicts = self.detect_conflicts()
        
        if to_square not in conflicts:
            # No conflict - this is Schrödinger's cat!
            # The capture happens without measurement
            return True, target_occupant
        
        return False, target_occupant  # There's a conflict, measurement needed
    
    def is_quantum_capturer(self, from_square: str) -> Optional[Tuple['QuantumPiece', str, float]]:
        """
        Check if the piece at from_square is a quantum piece in superposition.
        
        This is used when a quantum piece attempts to capture - we need to resolve
        which position is the "original" before allowing the capture.
        
        Args:
            from_square: Source square of the move (where the capturing piece is)
        
        Returns:
            Tuple of (quantum_piece, state_id, probability) if quantum, None otherwise
        """
        for qp in self.quantum_pieces:
            for state_id, state_data in qp.qnum.items():
                if state_data[0] == from_square:
                    # Found a quantum piece at the source square
                    return qp, state_id, state_data[1]
        return None
    
    def get_quantum_capturer_all_positions(self, from_square: str) -> Optional[Tuple['QuantumPiece', List[Tuple[str, float]]]]:
        """
        Get all positions of a quantum piece at from_square.
        
        Args:
            from_square: Source square of the move
        
        Returns:
            Tuple of (quantum_piece, list of (position, probability)) if quantum, None otherwise
        """
        for qp in self.quantum_pieces:
            # Check if this quantum piece has any state at from_square
            has_from_square = False
            positions = []
            for state_id, state_data in qp.qnum.items():
                positions.append((state_data[0], state_data[1]))
                if state_data[0] == from_square:
                    has_from_square = True
            
            if has_from_square:
                return qp, positions
        return None
    
    def resolve_quantum_capturer_measurement(self, from_square: str, to_square: str,
                                               capturing_piece_color: bool) -> Dict[str, Any]:
        """
        Resolve measurement when a quantum piece attempts to capture.
        
        Rules:
        - First resolve which position is the "original" (actual position of the piece)
        - If the right piece (actual position) is at from_square and attempts to capture:
          1. Remove other instances from board (FEN)
          2. Execute the capture
          3. Change capturing piece to classical piece
        - If the wrong piece (not at from_square) - capture fails, piece is at another position:
          1. Capture fails (no piece at from_square to capture)
          2. The piece becomes classical at its actual position
        
        Args:
            from_square: Source square where capture is attempted
            to_square: Target square of the capture
            capturing_piece_color: Color of the capturing piece
        
        Returns:
            Dictionary with measurement results and action to take
        """
        # Find the quantum piece that's attempting to capture
        capturer_result = self.get_quantum_capturer_all_positions(from_square)
        
        if not capturer_result:
            return {'success': False, 'error': 'No quantum piece at source square'}
        
        qp, positions = capturer_result
        piece_symbol = str(qp.piece)
        
        # Get total probability at from_square vs other positions
        prob_at_from = 0
        other_positions = []
        
        for pos, prob in positions:
            if pos == from_square:
                prob_at_from = prob
            else:
                other_positions.append((pos, prob))
        
        total_prob = sum(p for _, p in positions)
        
        # Randomly determine if piece is at from_square (attempting capture)
        # or at another position
        rand = random.random()
        piece_exists_at_from = rand < (prob_at_from / total_prob) if total_prob > 0 else False
        
        if piece_exists_at_from:
            # The RIGHT piece is capturing - it's actually at from_square
            # Remove other instances, let capture succeed, make piece classical
            
            # Remove other positions from quantum state
            states_to_remove = []
            for state_id in qp.qnum.keys():
                if qp.qnum[state_id][0] != from_square:
                    states_to_remove.append(state_id)
            
            for state_id in states_to_remove:
                del qp.qnum[state_id]
            
            # Set to 100% probability at from_square
            for state_id in qp.qnum.keys():
                qp.qnum[state_id] = [from_square, 1.0]
            
            return {
                'success': True,
                'action': 'capture_succeeds',
                'selected_piece': piece_symbol,
                'from_square': from_square,
                'to_square': to_square,
                'other_positions_removed': other_positions,
                'outcome': 'right_piece_capturing'
            }
        else:
            # The WRONG piece is attempting to capture - piece is actually at another position
            # Capture fails, piece becomes classical at actual position
            
            if other_positions:
                # Get the actual position (highest probability or first)
                actual_position, actual_prob = max(other_positions, key=lambda x: x[1])
                
                # Collapse to the actual position
                qp.qnum.clear()
                qp.qnum['0'] = [actual_position, 1.0]
                
                return {
                    'success': True,
                    'action': 'capture_fails_make_classical',
                    'selected_piece': piece_symbol,
                    'from_square': from_square,
                    'to_square': to_square,
                    'actual_position': actual_position,
                    'outcome': 'wrong_piece_attempting_capture'
                }
            
            return {
                'success': True,
                'action': 'capture_fails_no_position',
                'selected_piece': piece_symbol,
                'from_square': from_square,
                'outcome': 'piece_does_not_exist_at_capture_square'
            }

    def resolve_quantum_vs_quantum_capture(self, from_square: str, to_square: str,
                                           capturing_piece_color: bool) -> Dict[str, Any]:
        """
        Resolve measurement when a QUANTUM piece attempts to capture another QUANTUM piece.
        
        Three possible outcomes based on which pieces are "real":
        
        Instance 1 (Real Attacker + Real Defender):
        - Both pieces exist at their respective squares
        - Remove fake pieces of both
        - Attacker captures defender
        - Attacker piece changes to classical piece
        
        Instance 2 (Real Attacker + Fake Defender):
        - Attacker is at from_square, but defender is NOT at to_square
        - Remove fake instances of both defender and attacker
        - Attacker remains in original square (capture fails)
        
        Instance 3 (Fake Attacker + Fake Defender):
        - Neither piece exists at the attempted squares
        - Fake pieces are removed from board
        - Attacker remains on original square (capture fails)
        
        Args:
            from_square: Source square where capture is attempted (attacker's position)
            to_square: Target square of the capture (defender's position)
            capturing_piece_color: Color of the capturing piece
        
        Returns:
            Dictionary with measurement results and action to take:
            - instance: 1, 2, or 3
            - action: 'capture_succeeds', 'capture_fails', or 'both_fake'
            - attacker_piece: The attacking piece symbol
            - defender_piece: The defending piece symbol
            - attacker_actual_position: Where attacker actually is
            - defender_actual_position: Where defender actually is
            - attacker_other_positions: Other positions of attacker to remove
            - defender_other_positions: Other positions of defender to remove
        """
        # Get the quantum piece at from_square (attacker)
        attacker_result = self.get_quantum_capturer_all_positions(from_square)
        if not attacker_result:
            return {'success': False, 'error': 'No quantum piece at attacker square'}
        
        attacker_qp, attacker_positions = attacker_result
        attacker_piece = str(attacker_qp.piece)
        
        # Get the quantum piece at to_square (defender)
        defender_result = self.find_quantum_piece_at(to_square)
        if not defender_result:
            return {'success': False, 'error': 'No quantum piece at defender square'}
        
        defender_qp, defender_state = defender_result
        defender_piece = str(defender_qp.piece)
        
        # Get all positions for both pieces
        attacker_pos_list = [(pos, prob) for pos, prob in attacker_positions]
        defender_positions_all = [(state_id, data[0], data[1]) for state_id, data in defender_qp.qnum.items()]
        
        # Determine probabilities
        attacker_prob_at_from = sum(p for pos, p in attacker_pos_list if pos == from_square)
        attacker_total_prob = sum(p for _, p in attacker_pos_list)
        
        defender_prob_at_to = sum(data[1] for state_id, pos, data in defender_positions_all if pos == to_square)
        defender_total_prob = sum(data[1] for _, _, data in defender_positions_all)
        
        # Random measurement for attacker
        rand_attacker = random.random()
        attacker_exists = rand_attacker < (attacker_prob_at_from / attacker_total_prob) if attacker_total_prob > 0 else False
        
        # Random measurement for defender
        rand_defender = random.random()
        defender_exists = rand_defender < (defender_prob_at_to / defender_total_prob) if defender_total_prob > 0 else False
        
        # Determine which instance this is
        if attacker_exists and defender_exists:
            # Instance 1: Real Attacker + Real Defender
            # Both pieces exist - capture succeeds
            
            # Get other positions to remove
            attacker_other = [(pos, prob) for pos, prob in attacker_pos_list if pos != from_square]
            defender_other = [(pos, prob) for state_id, pos, prob in defender_positions_all if pos != to_square]
            
            # Collapse attacker to from_square (100%)
            for state_id in list(attacker_qp.qnum.keys()):
                if attacker_qp.qnum[state_id][0] != from_square:
                    del attacker_qp.qnum[state_id]
            for state_id in attacker_qp.qnum.keys():
                attacker_qp.qnum[state_id] = [from_square, 1.0]
            
            # Collapse defender to to_square (will be captured)
            for state_id in list(defender_qp.qnum.keys()):
                if defender_qp.qnum[state_id][0] != to_square:
                    del defender_qp.qnum[state_id]
            for state_id in defender_qp.qnum.keys():
                defender_qp.qnum[state_id] = [to_square, 1.0]
            
            return {
                'success': True,
                'instance': 1,
                'action': 'capture_succeeds',
                'attacker_piece': attacker_piece,
                'defender_piece': defender_piece,
                'from_square': from_square,
                'to_square': to_square,
                'attacker_actual_position': from_square,
                'defender_actual_position': to_square,
                'attacker_other_positions': attacker_other,
                'defender_other_positions': defender_other,
                'message': f'Instance 1: Real capture - {attacker_piece} at {from_square} captures {defender_piece} at {to_square}'
            }
            
        elif attacker_exists and not defender_exists:
            # Instance 2: Real Attacker + Fake Defender
            # Attacker is real, but defender is NOT at to_square
            
            # Find where defender actually is
            defender_actual_pos = None
            defender_other = []
            for state_id, pos, prob in defender_positions_all:
                if pos != to_square:
                    if defender_actual_pos is None or prob > defender_other[-1][1] if defender_other else False:
                        defender_actual_pos = pos
                    defender_other.append((pos, prob))
            
            # Get attacker's other positions to remove
            attacker_other = [(pos, prob) for pos, prob in attacker_pos_list if pos != from_square]
            
            # Collapse attacker to from_square (becomes classical)
            for state_id in list(attacker_qp.qnum.keys()):
                if attacker_qp.qnum[state_id][0] != from_square:
                    del attacker_qp.qnum[state_id]
            for state_id in attacker_qp.qnum.keys():
                attacker_qp.qnum[state_id] = [from_square, 1.0]
            
            # Remove defender quantum piece entirely (becomes classical at actual position)
            
            return {
                'success': True,
                'instance': 2,
                'action': 'capture_fails',
                'attacker_piece': attacker_piece,
                'defender_piece': defender_piece,
                'from_square': from_square,
                'to_square': to_square,
                'attacker_actual_position': from_square,
                'defender_actual_position': defender_actual_pos,
                'attacker_other_positions': attacker_other,
                'defender_other_positions': defender_other,
                'message': f'Instance 2: Real attacker {attacker_piece} at {from_square}, fake defender {defender_piece} at {to_square} (actual: {defender_actual_pos})'
            }
            
        elif not attacker_exists and not defender_exists:
            # Instance 3: Fake Attacker + Fake Defender
            # Neither piece exists at the attempted squares
            
            # Find where attacker actually is
            attacker_actual_pos = None
            attacker_other = []
            for pos, prob in attacker_pos_list:
                if pos != from_square:
                    if attacker_actual_pos is None or prob > (attacker_other[-1][1] if attacker_other else 0):
                        attacker_actual_pos = pos
                    attacker_other.append((pos, prob))
            
            # Find where defender actually is
            defender_actual_pos = None
            defender_other = []
            for state_id, pos, prob in defender_positions_all:
                if pos != to_square:
                    if defender_actual_pos is None or prob > (defender_other[-1][1] if defender_other else 0):
                        defender_actual_pos = pos
                    defender_other.append((pos, prob))
            
            return {
                'success': True,
                'instance': 3,
                'action': 'both_fake',
                'attacker_piece': attacker_piece,
                'defender_piece': defender_piece,
                'from_square': from_square,
                'to_square': to_square,
                'attacker_actual_position': attacker_actual_pos,
                'defender_actual_position': defender_actual_pos,
                'attacker_other_positions': attacker_other,
                'defender_other_positions': defender_other,
                'message': f'Instance 3: Fake attacker {attacker_piece} at {from_square} (actual: {attacker_actual_pos}), fake defender {defender_piece} at {to_square} (actual: {defender_actual_pos})'
            }
        
        # Edge case - shouldn't reach here
        return {
            'success': False,
            'error': 'Unexpected measurement result'
        }



def create_quantum_piece(position: str, piece: Any) -> QuantumPiece:

    """
    Factory function to create a quantum piece.
    """
    return QuantumPiece(position, piece)
