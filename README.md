# Update Recent Social Shares Script

A Python script that automatically updates social media engagement metrics for recent press coverage. Designed to run as a scheduled cron job to keep social metrics current.

## Overview

This script queries press coverage published within the last 10 days and fetches the latest social media engagement metrics from multiple platforms:
- **X (Twitter)**: tweets, bookmarks, favorites, quotes, replies, retweets
- **Facebook**: shares, comments, reactions
- **Reddit**: post count
- **Pinterest**: pin count

The script updates existing social share records or creates new ones as needed, tracking changes in engagement over time.

## Features

- 🔄 **Automatic Updates**: Designed to run twice daily via cron
- 📊 **Multi-Platform**: Aggregates metrics from X, Facebook, Reddit, and Pinterest
- 🎯 **Smart Updates**: Only updates records where metrics have changed
- 📈 **Change Tracking**: Shows before/after engagement metrics
- 🚦 **Rate Limiting**: Built-in delays to respect API limits
- 📝 **Detailed Logging**: Comprehensive output suitable for log files
- 🔍 **Dry Run Mode**: Preview changes without updating database

## Requirements

- Python 3.6+
- PostgreSQL database
- API keys for SharedCount and Twitter API

### Python Dependencies

```bash
pip install psycopg2-binary requests
```

## Environment Variables

The script requires the following environment variables:

```bash
# PostgreSQL database connection string
export DATABASE_URL="postgresql://user:password@host:port/database"

# SharedCount API key (for Facebook, Reddit, Pinterest metrics)
export SHAREDCOUNT_API_KEY="your_sharedcount_api_key"

# Twitter/X API key (via RapidAPI)
export TWITTER_API_KEY="your_twitter_api_key"
```

## Usage

### Basic Usage

Update coverage from the past 10 days:
```bash
python update_recent_social_shares.py
```

### Command Line Options

```bash
# Look back N days for coverage (default: 10)
python update_recent_social_shares.py --days 7

# Preview what would be updated without making changes
python update_recent_social_shares.py --dry-run

# Show trending coverage after update
python update_recent_social_shares.py --show-trending
```

## Cron Job Setup

To run the script automatically at 8 AM and 8 PM daily:

1. Open your crontab:
   ```bash
   crontab -e
   ```

2. Add this line:
   ```bash
   0 8,20 * * * /usr/bin/python3 /path/to/update_recent_social_shares.py >> /var/log/social_shares_update.log 2>&1
   ```

3. Ensure the script is executable:
   ```bash
   chmod +x update_recent_social_shares.py
   ```

### Alternative Cron Schedules

```bash
# Every 12 hours
0 */12 * * * /usr/bin/python3 /path/to/update_recent_social_shares.py

# Every 6 hours
0 */6 * * * /usr/bin/python3 /path/to/update_recent_social_shares.py

# Once daily at 2 AM
0 2 * * * /usr/bin/python3 /path/to/update_recent_social_shares.py
```

## Database Schema

The script works with two tables:

### agentcy_client_coverage_log
- Contains press coverage articles with URLs
- Key fields: `id`, `url`, `published`, `client`, `title`

### agentcy_client_coverage_social_shares
- Stores social media metrics for each coverage item
- Linked to coverage_log via `coverage_id`
- Tracks individual platform metrics and total engagement

## Output Example

```
🚀 Starting Recent Social Shares Update
============================================================
Time: 2024-12-09 08:00:01
Mode: LIVE
Days back: 10
SharedCount API: ✅ Configured
Twitter API: ✅ Configured
============================================================

📋 Found 25 coverage items from the past 10 days

🔄 Processing 1/25
   ID: 12345
   Client: TechCorp (ID: 42)
   Title: TechCorp Announces New AI Platform...
   URL: https://techcrunch.com/2024/12/08/techcorp-ai
   Published: 2024-12-08 14:30:00
   📊 Current engagement: 1,234
   Last updated: 2024-12-08 20:00:00
   📱 Fetching SharedCount data...
   ✅ SharedCount data received
      Reddit: 45, Pinterest: 12
      Facebook - Shares: 234, Comments: 56, Reactions: 89
   🐦 Fetching X (Twitter) data...
   ✅ X data received
      Tweets: 67, Bookmarks: 123, Favorites: 456
      Quotes: 23, Replies: 89, Retweets: 234
   📈 Engagement changed: 1,234 → 1,589 (+355)
   💾 Saving social data to database...
   ✅ Social data updated successfully
   📊 Total engagement: 1,589

[... continues for all records ...]

============================================================
📊 Update Complete!
============================================================
   Started: 2024-12-09 08:00:01
   Finished: 2024-12-09 08:02:34
   Duration: 0:02:33

   Total processed: 25
   ✅ Updated: 18
   🆕 New records: 3
   ⏸️  Unchanged: 2
   ❌ Failed: 2

   Success rate: 84.0%
============================================================
```

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Verify DATABASE_URL is set correctly
   - Check network connectivity to database
   - Ensure database user has required permissions

2. **API Key Errors**
   - Verify API keys are set in environment variables
   - Check API key validity and rate limits
   - SharedCount has a free tier limit of 500 requests/day

3. **No Records Found**
   - Check if there's recent coverage in the database
   - Verify the `published` column has recent dates
   - Try increasing `--days` parameter

### Debug Mode

For detailed troubleshooting, run with verbose output:
```bash
python update_recent_social_shares.py --dry-run
```

## Performance Considerations

- The script includes a 1-second delay between API requests to avoid rate limiting
- Processing 100 articles typically takes 3-5 minutes
- Database queries are optimized to only fetch necessary records
- Consider running during off-peak hours for better API performance

## Monitoring

To monitor the script's performance over time:

```bash
# Check recent log entries
tail -n 100 /var/log/social_shares_update.log

# Count successful vs failed updates
grep "Update Complete" /var/log/social_shares_update.log | tail -n 10

# Monitor for errors
grep "ERROR\|Failed" /var/log/social_shares_update.log
```
