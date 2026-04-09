#!/bin/bash
# Test script for the mailarchive message worker

set -e

WORKER_URL="${WORKER_URL:-http://localhost:8787}"
LIST="dnsop"
HASH="aBcDeFgHiJkLmNoPqRsTuVwXyZ1"

echo "Testing Mailarchive Message Worker"
echo "===================================="
echo ""

echo "1. Test public message (should serve from R2 if available)"
curl -s -i "${WORKER_URL}/arch/msg/${LIST}/${HASH}/" | head -20
echo ""
echo ""

echo "2. Test with authentication (should proxy to origin)"
curl -s -i -H "Cookie: sessionid=test" "${WORKER_URL}/arch/msg/${LIST}/${HASH}/" | head -15
echo ""
echo ""

echo "3. Test invalid URL (should proxy to origin)"
curl -s -i "${WORKER_URL}/arch/msg/${LIST}/tooshort/" | head -15
echo ""
echo ""

echo "4. Test non-message path (should proxy to origin)"
curl -s -i "${WORKER_URL}/arch/browse/${LIST}/" | head -15
echo ""
echo ""

echo "5. Test with API key (should proxy to origin)"
curl -s -i "${WORKER_URL}/arch/msg/${LIST}/${HASH}/?apikey=test" | head -15
echo ""
echo ""

echo "Tests complete!"
echo ""
echo "Check the X-Served-By and X-Worker-Action headers to see how each request was handled."
