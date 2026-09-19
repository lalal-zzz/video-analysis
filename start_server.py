#!/usr/bin/env python
"""Start web server"""
import uvicorn
from web.app import app
uvicorn.run(app, host='127.0.0.1', port=8080, workers=1, access_log=False)
