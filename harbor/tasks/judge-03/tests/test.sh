#!/bin/bash
# Asks the sim sidecar for the final score. Any failure leaves the reward at 0.
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
curl -sS --fail --max-time 240 -X POST -H "Authorization: Bearer dd9a7ce930dbd1b905a01b22997bdb5b37ddcd4d27bd75e60028e2d467c03e30" \
  http://oncall-sim:8000/admin/finalize -o /logs/verifier/reward_breakdown.json || exit 0
python3 - <<'EOF' || echo 0 > /logs/verifier/reward.txt
import json
score = float(json.load(open("/logs/verifier/reward_breakdown.json"))["score"])
open("/logs/verifier/reward.txt", "w").write(str(score))
EOF
exit 0
