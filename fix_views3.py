# Script to fix the duplicate elif block in views.py
with open('quantum_chess/views.py', 'r') as f:
    lines = f.readlines()

# Find and remove the duplicate elif block
new_lines = []
skip_until_next_comment = False
found_duplicate = False

i = 0
while i < len(lines):
    line = lines[i]
    
    # Look for the second occurrence of "elif action == 'capture_fails_no_position':"
    # that is followed by just adding to quantum_pieces_data
    if "elif action == 'capture_fails_no_position':" in line:
        # Check if this is the second occurrence (the duplicate)
        # Look ahead to see if it's followed by simple quantum_pieces_data assignment
        j = i + 1
        while j < len(lines) and (lines[j].strip() == '' or lines[j].strip().startswith('#')):
            j += 1
        
        if j < len(lines):
            next_line = lines[j].strip()
            # Check if it's the simple version (the duplicate)
            if 'quantum_pieces_data = []' in next_line and 'for qp in quantum_game.quantum_pieces' in lines[j+1]:
                # This is the duplicate - skip it
                found_duplicate = True
                # Skip this entire block until we find the next "# Record measurement"
                while i < len(lines) and "# Record measurement in move history" not in lines[i]:
                    i += 1
                continue
    
    new_lines.append(line)
    i += 1

if found_duplicate:
    print("Found and removed duplicate code")
else:
    print("Duplicate not found - checking if file is already correct")
    # Restore from original
    new_lines = lines

with open('quantum_chess/views.py', 'w') as f:
    f.writelines(new_lines)

print("Done!")
