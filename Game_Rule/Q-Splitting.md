# Quantum Splitting

Quantum Splitting is a unique move in Quantum Chess that allows a piece to exist in two different positions simultaneously in superposition.

## Overview

When a player performs a **Quantum Split**, a single piece is divided into two copies that occupy different squares at the same time. Each copy has 50% probability of being the "real" piece until a measurement occurs.

## How Quantum Split Works

### Basic Mechanics

1. **Select a piece**: Choose any piece from its current position
2. **Choose two destinations**: Select two different legal target squares
3. **Execute the split**: The piece is placed in superposition at both target squares

### Probability Distribution

When a piece is split:
- The original position is removed from the board
- The piece appears at **both** target squares
- Each copy has **50% probability** (half of the original 100%)
- The piece remains in superposition until measured

```
Example:
- White Knight at E1 splits to C1 and F1
- After split: 50% chance Knight is at C1, 50% chance at F1
```

## Rules and Restrictions

### 1. Legal Move Validation

Both target squares **must** be valid legal moves for the piece being split:
- The piece must be able to legally move to each target square
- This follows standard chess movement rules for each piece type

### 2. No Capturing on Split

**Capturing is NOT allowed during quantum split:**
- Both target squares must be **empty**
- If either target square contains a piece (friendly or enemy), the split is illegal
- This prevents ambiguous capture scenarios

### 3. Existing Quantum Pieces

If a piece is already in quantum superposition:
- The split creates additional branches in its quantum state
- Probability is divided among all resulting positions

## Board State After Split

After a successful quantum split:
1. The original square becomes empty
2. Both target squares contain the same piece
3. The turn passes to the opponent
4. Quantum mode is automatically enabled

## Measurement and Collapse

### When Does a Split Piece Collapse?

A quantum piece collapses (becomes a single definite position) when:

1. **Capture occurs**: The piece is captured or captures another piece
2. **Explicit measurement**: A measurement is performed on the piece
3. **Conflict detection**: The piece occupies a square with another different piece in superposition

### Collapse Outcome

When measured:
- One position is randomly selected based on probability (50% each for a simple split)
- The piece at the non-selected position is removed
- The remaining piece becomes a classical (non-quantum) piece

```
Example:
- Split Knight at C1 (50%) and F1 (50%)
- Measurement occurs
- Result: Knight collapses to either C1 or F1 with 100% certainty
```

## Technical Implementation

### State Representation

Each quantum piece tracks:
- **qnum**: Dictionary of quantum states
  - Format: `{state_id: [position, probability]}`
  - Example: `{'0': ['c1', 0.5], '1': ['f1', 0.5]}`

### Split Algorithm

```
python
def split(self, i_add: str, pos1: str, pos2: str):
    # Create two new states from the original
    self.qnum[i_add + '0'] = ["", 0]
    self.qnum[i_add + '1'] = ["", 0]
    
    # Assign positions
    self.qnum[i_add + '0'][0] = pos1
    self.qnum[i_add + '1'][0] = pos2
    
    # Divide probability equally
    self.qnum[i_add + '0'][1] = self.qnum[i_add][1] / 2.0
    self.qnum[i_add + '1'][1] = self.qnum[i_add][1] / 2.0
    
    # Remove original state
    del self.qnum[i_add]
```

## Examples

### Example 1: Knight Split

```
Before Split:
. . . . . . . .
. . . . . . . .
. . . . . . . .
. . . . . . . .
. . . . N . . .  (E1: White Knight)
. . . . . . . .
. . . . . . . .
. . . . . . . .

Action: Split Knight from E1 to C1 and F1

After Split:
. . . . . . . .
. . . . . . . .
. . . . . . . .
. . . . . . . .
. . . . . . . .
. . N . . N . .  (C1 and F1: White Knight in superposition)
. . . . . . . .
. . . . . . . .

The Knight now exists at both C1 and F1 with 50% probability each.
```

### Example 2: Pawn Split

```
Before Split:
. . . . . . . .
. . p . . . . .  (A2: Black Pawn)
. . . . . . . .
. . . . . . . .
. . P . . . . .  (A3: White Pawn)
. . . . . . . .
. . . . . . . .
. . . . . . . .

Action: Split White Pawn from A3 to A4 and B4 (if legal)

After Split:
. . . . . . . .
. . p . . . . .
. . . . . . . .
. . P P . . . .  (A4 and B4: White Pawn in superposition)
. . . . . . . .
. . . . . . . .
. . . . . . . .
. . . . . . . .
```

## Strategic Considerations

### Advantages of Quantum Splitting

1. **Uncertainty**: Opponent cannot know which position you'll occupy
2. **Fork potential**: Threaten two squares simultaneously
3. **Escape danger**: Split to avoid capture when path is uncertain

### Risks

1. **Reduced piece power**: Each position has only 50% strength
2. **Self-conflict**: If both split positions become occupied, measurement triggers
3. **Predictability**: Experienced opponents can predict likely collapse outcomes

## Related Rules

- [Superpositions](Game%20Rules/2.-Superpositions.md) - Understanding piece states
- [Measurements](Game%20Rules/3.-Measurements.md) - How and when collapse occurs
- [Making Moves](Game%20Rules/1.-Making-moves.md) - General move rules
