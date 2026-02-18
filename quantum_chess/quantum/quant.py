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
            if i.startswith(add):
                del self.qnum[i]
            else:
                probs += self.qnum[i][1]
        
        # Normalize probabilities
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
        
        # Detangle entangled pieces
        for i in range(len(self.ent)):
            if final_state.startswith(self.ent[i][2]):
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



def create_quantum_piece(position: str, piece: Any) -> QuantumPiece:
    """
    Factory function to create a quantum piece.
    """
    return QuantumPiece(position, piece)
