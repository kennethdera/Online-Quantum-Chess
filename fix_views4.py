# Script to fix the ==== lines in views.py
with open('quantum_chess/views.py', 'r') as f:
    content = f.read()

# Remove the problematic ======= lines
content = content.replace('                    })\n=======\n                elif action == \'capture_fails_no_position\':', 
                         '                    })\n                elif action == \'capture_fails_no_position\':')

with open('quantum_chess/views.py', 'w') as f:
    f.write(content)

print("Fixed!")
