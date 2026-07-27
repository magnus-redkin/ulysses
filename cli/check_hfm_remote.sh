#!/bin/bash
# check_hfm_remote.sh — запускается на Brain, дёргает HFM по SSH, алерт при FAIL

RESULT=$(ssh 45.131.215.185 '~/restore/check_hfm.sh' 2>&1)

if echo "$RESULT" | grep -q "ALERT:"; then
    MSG=$(echo "$RESULT" | grep "ALERT:" | head -1 | sed 's/ALERT: //')
    cd "$HOME/Ulysses"
    .venv/bin/python3 -c "
import asyncio
from cli.notify import send_admin_alert
asyncio.run(send_admin_alert('HFM Alert: $MSG'))
"
fi
