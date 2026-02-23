# Script to fix the duplicate code in views.py
with open('quantum_chess/views.py', 'r') as f:
    content = f.read()

# Fix the duplicate elif block
old_pattern = """                    })
=======
                elif action == 'capture_fails_no_position':
                    # The piece doesn't exist at all - just remove from quantum pieces
                    quantum_pieces_data = []
                    for qp in quantum_game.quantum_pieces:
                        quantum_pieces_data.append({
                            'piece': str(qp.piece),
                            'qnum': qp.qnum,
                            'entangled': [[str(e[0].piece) if e[0] else None, e[1], e[2]] for e in qp.ent]
                        })
=======
                elif action == 'capture_fails_no_position':"""

new_pattern = """                    })
=======
                elif action == 'capture_fails_no_position':"""

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    print("Fixed duplicate code")
else:
    print("Pattern not found, trying alternate...")

with open('quantum_chess/views.py', 'w') as f:
    f.write(content)

print("Done!")
