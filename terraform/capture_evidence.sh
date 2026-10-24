#!/bin/bash
echo "=== docker ps ==="
docker ps --filter "name=llm-monitor" --format "{{.Names}}	{{.Image}}	{{.Status}}	{{.Ports}}"
echo
echo "=== prometheus healthy ==="
curl -s http://localhost:9191/-/healthy
echo
echo
echo "=== prometheus rules (names + health) ==="
curl -s http://localhost:9191/api/v1/rules | python3 -c "
import json, sys
d = json.load(sys.stdin)
for g in d['data']['groups']:
    for r in g['rules']:
        print(r['name'], r['health'])
"
echo
echo "=== grafana health ==="
curl -s http://localhost:3001/api/health
echo
echo
echo "=== grafana datasource ==="
curl -s -u admin:admin http://localhost:3001/api/datasources | python3 -m json.tool
