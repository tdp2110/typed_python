import sys
import generate_types

if len(sys.argv) > 1:
    generate_types.generate_some_types(sys.argv[1])
else:
    print(f"usage: {sys.argv[0]} destination")