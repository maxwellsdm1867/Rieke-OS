"""Seed project navigation before React paints on each local project address."""
import json
from flask import Response, send_from_directory


def project_frontend_response(frontend, path, inventory):
    if path != 'index.html':
        return send_from_directory(frontend, path)
    response = send_from_directory(frontend, path, conditional=False)
    response.direct_passthrough = False
    data = json.dumps(inventory(), ensure_ascii=True).replace('<', '\\u003c')
    bootstrap = '<script type="application/json" id="rieke-projects-bootstrap">' + data + '</script>'
    try:
        html = response.get_data(as_text=True).replace('</head>', bootstrap + '</head>', 1)
    finally:
        response.close()
    return Response(html, mimetype='text/html', headers={'Cache-Control': 'no-store'})
