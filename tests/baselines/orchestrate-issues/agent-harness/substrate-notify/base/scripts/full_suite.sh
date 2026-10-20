#!/bin/sh
echo "running integration + replay suites (slow)..."
sleep 150
python3 -m unittest discover -s tests -q
