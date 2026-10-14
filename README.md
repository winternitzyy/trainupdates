# Train updates

Texts you when **c2c** or the **Suffragette line** (London Overground, Gospel Oak to Barking Riverside) has problems, and again when the line is back to Good Service.

Line statuses come from the [TfL Unified API](https://api.tfl.gov.uk/). SMS messages are sent through [Twilio](https://www.twilio.com/). A GitHub Actions workflow checks the lines every 10 minutes from 05:00 to midnight UTC.

## Setup

1. Create a Twilio account and get a phone number that can send SMS to UK numbers.
2. Optional: register at the [TfL API portal](https://api-portal.tfl.gov.uk/) for an app key, which raises the rate limit.
3. In the GitHub repo, go to **Settings → Secrets and variables → Actions** and add these secrets:

   | Secret | Example |
   |---|---|
   | `TWILIO_ACCOUNT_SID` | `ACxxxxxxxx...` |
   | `TWILIO_AUTH_TOKEN` | your Twilio auth token |
   | `TWILIO_FROM_NUMBER` | `+447700900000` |
   | `ALERT_TO_NUMBER` | `+447700900123` (separate several numbers with commas) |
   | `TFL_APP_KEY` | optional |

4. Merge to the default branch. Scheduled workflows only run there. To test straight away, open **Actions → Train alerts → Run workflow**.

## Example messages

```
c2c: Severe Delays. C2C: Signal failure at Upminster. Trains may be cancelled or delayed by up to 20 minutes.
c2c: back to Good Service.
```

## Run locally

```sh
DRY_RUN=1 python train_alerts.py   # prints messages without sending them
python -m unittest discover -s tests
```

To watch other lines, set `TRAIN_LINES` to TfL line IDs, for example `c2c,suffragette,district`.
