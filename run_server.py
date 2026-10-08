import os
import sys
import uvicorn

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

if __name__ == "__main__":
    print("Starting IT Chronicles Newsletter Automation Server at http://127.0.0.1:8000")
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
