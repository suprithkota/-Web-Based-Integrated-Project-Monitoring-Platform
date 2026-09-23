import sys
import os
from pathlib import Path

# Add project root to sys.path so app, routes, services can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Signal Netlify serverless environment
os.environ['NETLIFY'] = 'true'

# Import local awsgi adapter
from netlify.functions import awsgi
from app import app

def handler(event, context):
    return awsgi.response(app, event, context)
