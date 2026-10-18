# Train updates

Texts you when **c2c** or the **Suffragette line** (London Overground, Gospel Oak to Barking Riverside) has problems, and again when the line is back to Good Service.

Line statuses come from the [TfL Unified API](https://api.tfl.gov.uk/). For c2c, live status comes first from c2c's own website (the same status box shown on c2c-online.co.uk), which usually reports problems before anyone else; National Rail's Knowledgebase Incidents feed adds start times and the weekend's planned works (needs the `NR_INCIDENTS_KEY` secret from the Rail Data Marketplace). If either is unavailable, TfL is used. Texts are sent either from an Android phone's own SIM (via [ntfy](https://ntfy.sh) and Tasker, see below) or through [PureSMS](https://www.puresms.co.uk/). A GitHub Actions workflow checks the lines every minute, except between midnight and 05:00 UK time. Each run checks for about 5.5 hours and then starts the next run itself. A backup schedule every 2 hours restarts the chain if a run fails.

The repo needs to be public: Actions minutes are free and unlimited for public repos, but running all day would use up a private repo's monthly allowance. Your secrets stay private either way.

Every Thursday from 18:00 UK time you also get one text previewing the coming weekend: whether each line is running normally or has planned works on Saturday and Sunday, for example:

```
Traincliff Alerts: Train status for the coming weekend.
Sat 17 Oct: c2c: running normally, no planned works. Suffragette: running normally, no planned works.
Sun 18 Oct: c2c: running normally, no planned works. Suffragette: Part Closure. No service between Barking and Barking Riverside, please use local London Buses services.
```

Over Shabbat and Yom Tov no texts are sent. The pause starts at candle lighting in Westcliff-on-Sea (18 minutes before sunset the evening before) and ends 72 minutes after sunset on the last day (Rabbeinu Tam), with 5 extra minutes either side. Yom Tov follows the diaspora calendar (two-day festivals), and back-to-back Yom Tov and Shabbat days are treated as one pause. `python scripts/verify_shabbat.py` checks the dates and times against Hebcal. When it ends you get one text only if a line is still disrupted, saying when the disruption started:

```
Traincliff Alerts: c2c: Severe Delays since Sat 14:32. Signal failure at Upminster. Still disrupted.
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
5. To check SMS works, open **Actions → Send test SMS → Run workflow**. Pick **Current status**, **Weekend preview** or **After Shabbat**.

## Who reports c2c disruptions first

Each c2c disruption gets a row in [`disruption_log.csv`](disruption_log.csv): the time c2c's website, TfL and National Rail each first reported it, which was first, and by how many minutes. c2c and TfL times are when our minute-by-minute check first saw the problem; the National Rail time is when it created the incident. The file is updated at the end of each 5.5-hour run, and no times are recorded during quiet hours or Shabbat/Yom Tov.

## How the next trains are running

When a line is reported disrupted, updated, or back to Good Service, the text also lists the next 3 trains each way on both legs of the journey, read from live departure boards only at the moment the text is sent:

- Suffragette: STO to BKG and BKG to STO, from the same National Rail staff boards, with TfL's live board (no key needed) as the fallback if National Rail can't be read.
- c2c: WCF to BKG and BKG to WCF, from National Rail's Live Arrival and Departure Boards - Staff Version on the Rail Data Marketplace (TfL has no live boards for c2c). Needs its consumer key as the secret `NR_LDB_KEY`; without it c2c texts just leave the trains out.

Each train is written as cancelled, *N* minutes delayed, or on time, e.g. `STO to BKG: 14:05 cancelled, 14:20 3 minutes delayed, 14:35 on time.`

## Sending texts from a phone (ntfy + Tasker)

When the `NTFY_TOPIC` secret is set, each text is published to that [ntfy](https://ntfy.sh) topic instead of PureSMS. An Android phone subscribed to the topic passes it to Tasker, which sends it as an SMS from the phone's SIM. If ntfy can't be reached and the PureSMS secrets are still set, the text goes through PureSMS instead.

On the phone:

1. Install **ntfy** and **Tasker**. Turn off battery optimisation for both (Settings → Apps → *app* → Battery → Unrestricted).
2. In ntfy, subscribe to a topic with a long random name, e.g. `trainalerts-7Kq9xV2mPz4w`. Anyone who knows the name can post to it, so keep it private.
3. In Tasker, create a profile named `Train alerts`: **Event → System → Intent Received**, Action `io.heckel.ntfy.MESSAGE_RECEIVED`.
4. Give it a task:
   - **If** `%topic` `~` *your topic name*
   - **Phone → Send SMS**: Number *the number to text*, Message `%message` (one Send SMS per recipient)
   - **End If**
5. Test: in the ntfy app, open the topic and send `Test from ntfy`. The phone should text it to you.
6. In GitHub, add the topic name as the secret `NTFY_TOPIC`. Then run **Actions → Send test SMS** to check the whole path.

Optional pause by text: add profiles **Event → Phone → Received Text** (Sender: your number, Content `STOP` / `START`) whose tasks run **Tasker → Profile Status**, Name `Train alerts`, Set Off / On.

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
