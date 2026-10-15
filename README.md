# Train updates

Texts you when **c2c** or the **Suffragette line** (London Overground, Gospel Oak to Barking Riverside) has problems, and again when the line is back to Good Service.

Line statuses come from the [TfL Unified API](https://api.tfl.gov.uk/). SMS messages are sent through [PureSMS](https://www.puresms.co.uk/). A GitHub Actions workflow checks the lines every minute, except between midnight and 05:00 UK time. Each run checks for about 5.5 hours and then starts the next run itself. A backup schedule every 2 hours restarts the chain if a run fails.

The repo needs to be public: Actions minutes are free and unlimited for public repos, but running all day would use up a private repo's monthly allowance. Your secrets stay private either way.

Every Thursday from 18:00 UK time you also get one text previewing the coming Sunday: whether each line is running normally or has planned works, for example:

```
Sunday 18 Oct: c2c: Planned Closure. No trains between Barking and Upminster. Suffragette: running normally, no planned works.
```

## Setup

1. In your PureSMS dashboard, set up a sender (for example `TrainAlert`, up to 11 letters) and create an API key.
2. Optional: register at the [TfL API portal](https://api-portal.tfl.gov.uk/) for an app key, which raises the rate limit.
3. In the GitHub repo, go to **Settings → Secrets and variables → Actions** and add these secrets:

   | Secret | Example |
   |---|---|
   | `PURESMS_API_KEY` | your PureSMS API key |
   | `PURESMS_SENDER` | `TrainAlert` (must match the sender in your dashboard) |
   | `ALERT_TO_NUMBER` | `+447700900123` (separate several numbers with commas) |
   | `TFL_APP_KEY` | optional |

4. Make sure this is on the default branch, then open **Actions → Train alerts → Run workflow** to start checking.
5. To check SMS works, open **Actions → Send test SMS → Run workflow**. Pick **Current status** or **Sunday preview**.

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
