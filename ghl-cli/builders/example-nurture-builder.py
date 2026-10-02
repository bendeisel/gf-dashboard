"""Example: build a 3-email nurture sequence workflow in GHL.

A minimal, runnable reference for the workflow-builder API
(`cli_anything.gohighlevel.utils.workflow_builder`). Copy this file,
swap in your own tags, waits, and email copy, and deploy.

Flow: add tag -> wait 5m -> E1 -> wait 1d -> E2 -> wait 2d -> E3
      -> remove tag -> goal (exit early when the contact converts).

The workflow is created as DRAFT -- nothing sends until you review it
in the GHL UI and flip it live yourself.

Usage:
    set -a && source .env && set +a       # needs GHL_LOCATION_ID + Firebase token
    python3 builders/example-nurture-builder.py --dry-run
    python3 builders/example-nurture-builder.py
"""
import argparse
import json
import os
import sys
from pathlib import Path

from cli_anything.gohighlevel.utils.workflow_builder import (
    CampaignBuilder,
    email_step,
    goal_step,
    link_steps,
    tag_step,
    validate_campaign,
    wait_step,
)
from cli_anything.gohighlevel.utils.ghl_internal_client import (
    InternalGHLClient,
    TokenManager,
)

# === Config -- edit these ====================================================

WORKFLOW_NAME = "Example - 3-Email Nurture"
FROM_NAME = "Your Name"
START_TAG = "example-nurture"          # adding this tag enters the contact
GOAL_TAGS = ["purchase:complete"]      # any of these tags exits the sequence

# (wait value, wait unit, subject, body) per email, in send order.
EMAILS = [
    (5, "minutes",
     "Welcome -- here's what happens next",
     "<p>Hey {{contact.first_name}},</p>"
     "<p>Thanks for signing up. Over the next few days I'll send you a "
     "short series on getting started.</p>"),
    (1, "days",
     "The one mistake to avoid",
     "<p>Most people skip the setup step and pay for it later. "
     "Here's the 5-minute version...</p>"),
    (2, "days",
     "Ready when you are",
     "<p>That's the whole series. When you're ready to go further, "
     "reply to this email.</p>"),
]


# === Build ===================================================================

def build_campaign() -> dict:
    raw_steps = [tag_step(f"Add {START_TAG}", [START_TAG])]
    for i, (val, unit, subject, body) in enumerate(EMAILS, start=1):
        raw_steps.append(wait_step(f"Wait {val} {unit} before E{i}", val, unit))
        raw_steps.append(email_step(f"Email E{i}: {subject[:48]}", subject,
                                    body, from_name=FROM_NAME))
    raw_steps.append(tag_step(f"Remove {START_TAG}", [START_TAG], remove=True))
    raw_steps.append(goal_step("Exit on conversion", GOAL_TAGS))

    return {
        "example_nurture": {
            "name": WORKFLOW_NAME,
            "goal_tags": GOAL_TAGS,
            "templates": link_steps(raw_steps),
        }
    }


# === Main ====================================================================

def main():
    parser = argparse.ArgumentParser(description="Deploy the example nurture to GHL")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and print the campaign summary only")
    parser.add_argument("--folder-id", type=str, default=None,
                        help="Existing GHL folder to deploy into (optional)")
    args = parser.parse_args()

    campaign = build_campaign()
    errors = validate_campaign(campaign)
    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    config = campaign["example_nurture"]
    print(f"Campaign: {config['name']}")
    print(f"Steps:    {len(config['templates'])}")
    print(f"Trigger:  tag '{START_TAG}' added")
    print(f"Goal:     exit on {', '.join(config['goal_tags'])}")

    if args.dry_run:
        out = Path("/tmp/example-nurture-campaign.json")
        out.write_text(json.dumps(campaign, indent=2, default=str))
        print(f"\nDRY RUN -- full campaign JSON written to {out}")
        return

    location_id = os.environ.get("GHL_LOCATION_ID", "").strip()
    if not location_id:
        print("Error: GHL_LOCATION_ID is not set. Add it to your .env "
              "(see docs/get-firebase-token.md for the full setup).")
        sys.exit(1)

    client = InternalGHLClient(TokenManager(), location_id)
    print(f"\nCreating workflow in location {location_id} (DRAFT)...")
    builder = CampaignBuilder(client)
    builder.build(campaign, folder_id=args.folder_id)
    print()
    print(builder.format_summary())
    print()
    print("NEXT STEPS (manual, in the GHL UI):")
    print("  1. Open the workflow link above and review every step.")
    print("  2. Test-send each email to yourself.")
    print("  3. Flip Draft -> Live when it looks right.")


if __name__ == "__main__":
    main()
