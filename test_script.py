#!/usr/bin/env python3
import sys

print("This is a test script", flush=True)
sys.stdout.write("Direct write to stdout\n")
sys.stdout.flush()

print("If you see this, Python execution is working correctly", flush=True)
input("Press Enter to continue...") 