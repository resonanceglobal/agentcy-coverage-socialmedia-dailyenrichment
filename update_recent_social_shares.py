#!/usr/bin/env python3
"""
Update Recent Social Shares Script
Updates social media engagement metrics for coverage published in the past 10 days

This script is designed to run twice daily via cron job to keep social metrics current
for recent press coverage.

Usage:
    python update_recent_social_shares.py [--days N] [--dry-run]

Options:
    --days N      Look back N days for coverage (default: 10)
    --dry-run     Show what would be updated without making changes
"""

import argparse
import sys
import os
import time
import requests
import http.client
import urllib.parse
import json
from datetime import datetime, timedelta
import psycopg
from psycopg.rows import RealDictRow

# Database connection from environment
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable not set")
    sys.exit(1)


def connect_db():
    """Connect to database using environment variable"""
    try:
        return psycopg.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)


class RecentSocialSharesUpdater:
    def __init__(self, days_back=10, dry_run=False):
        self.days_back = days_back
        self.dry_run = dry_run
        self.processed = 0
        self.updated = 0
        self.new_records = 0
        self.failed = 0
        self.unchanged = 0
        self.total_records = 0

        # API Keys from environment
        self.sharedcount_api_key = os.environ.get("SHAREDCOUNT_API_KEY")
        self.twitter_api_key = os.environ.get("TWITTER_API_KEY")

        if not self.sharedcount_api_key:
            print("⚠️  WARNING: SHAREDCOUNT_API_KEY not set in environment")
        if not self.twitter_api_key:
            print("⚠️  WARNING: TWITTER_API_KEY not set in environment")

    def run(self):
        """Main execution method"""
        start_time = datetime.now()

        print(f"🚀 Starting Recent Social Shares Update")
        print(f"{'=' * 60}")
        print(f"Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"Days back: {self.days_back}")
        print(f"SharedCount API: {'✅ Configured' if self.sharedcount_api_key else '❌ Missing'}")
        print(f"Twitter API: {'✅ Configured' if self.twitter_api_key else '❌ Missing'}")
        print(f"{'=' * 60}\n")

        # Get records to process
        records = self.get_recent_coverage()

        if not records:
            print("✅ No recent coverage found to update")
            return

        print(f"📋 Found {len(records)} coverage items from the past {self.days_back} days\n")

        # Store total for use in process_record
        self.total_records = len(records)

        # Process each record
        for record in records:
            self.process_record(record)

            # Rate limiting between requests
            if self.processed < len(records):
                time.sleep(1)  # 1 second between requests

        # Show summary
        self.show_summary(start_time)

    def get_recent_coverage(self):
        """Get coverage records published in the past N days"""
        print(f"🔍 Querying for coverage published in the past {self.days_back} days...")

        conn = connect_db()
        cur = conn.cursor(row_factory=RealDictRow)

        try:
            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=self.days_back)

            query = """
                SELECT 
                    cl.id,
                    cl.client,
                    cl.client_id,
                    cl.title,
                    cl.url,
                    cl.published,
                    cl.created_at,
                    ss.coverage_id as has_social_data,
                    ss.x_tweet_count,
                    ss.x_bookmark_count,
                    ss.x_favorite_count,
                    ss.facebook_share_count,
                    ss.reddit_count,
                    ss.pinterest_count,
                    ss.total_social_engagement_count,
                    ss.updated_at as last_social_update
                FROM agentcy_client_coverage_log cl
                LEFT JOIN agentcy_client_coverage_social_shares ss ON cl.id = ss.coverage_id
                WHERE cl.published >= %s
                AND cl.url IS NOT NULL
                AND cl.deleted = false
                ORDER BY cl.published DESC
            """

            cur.execute(query, (cutoff_date,))
            records = cur.fetchall()

            # Convert to list of dicts for easier handling
            return [dict(row) for row in records]

        except Exception as e:
            print(f"❌ Database query error: {e}")
            return []
        finally:
            cur.close()
            conn.close()

    def process_record(self, record):
        """Process a single coverage record"""
        self.processed += 1

        print(f"\n🔄 Processing {self.processed}/{self.total_records}")
        print(f"   ID: {record['id']}")
        print(f"   Client: {record['client']} (ID: {record['client_id']})")
        print(f"   Title: {record['title'][:80]}...")
        print(f"   URL: {record['url']}")
        print(f"   Published: {record['published']}")

        if record['has_social_data']:
            print(f"   📊 Current engagement: {record['total_social_engagement_count']:,}")
            print(f"   Last updated: {record['last_social_update']}")
        else:
            print(f"   🆕 No social data yet - will create new record")

        if self.dry_run:
            print(f"   🔍 DRY RUN - Would fetch new metrics")
            return

        try:
            # Get current metrics
            facebook_data, reddit_count, pinterest_count = self.get_sharedcount_data(record['url'])
            x_data = self.get_x_data(record['url'])

            # Calculate total engagement
            total_engagement = (
                    x_data['tweets'] +
                    x_data['bookmarks'] +
                    x_data['favorites'] +
                    x_data['quotes'] +
                    x_data['replies'] +
                    x_data['retweets'] +
                    reddit_count +
                    facebook_data['share_count'] +
                    facebook_data['comment_count'] +
                    facebook_data['reaction_count'] +
                    pinterest_count
            )

            # Check if metrics changed
            if record['has_social_data']:
                old_total = record['total_social_engagement_count'] or 0
                if total_engagement != old_total:
                    print(f"   📈 Engagement changed: {old_total:,} → {total_engagement:,} "
                          f"({'+' if total_engagement > old_total else ''}{total_engagement - old_total:,})")
                else:
                    print(f"   ⏸️  No change in engagement metrics")
                    self.unchanged += 1
                    return

            # Save to database
            if self.save_social_data(
                    record['id'],
                    x_data,
                    facebook_data,
                    reddit_count,
                    pinterest_count,
                    total_engagement,
                    record['has_social_data']
            ):
                if record['has_social_data']:
                    print(f"   ✅ Social data updated successfully")
                    self.updated += 1
                else:
                    print(f"   ✅ Social data created successfully")
                    self.new_records += 1
                print(f"   📊 Total engagement: {total_engagement:,}")
            else:
                print(f"   ❌ Failed to save social data")
                self.failed += 1

        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            self.failed += 1

    def get_sharedcount_data(self, url):
        """Get social share data from SharedCount API"""
        print(f"   📱 Fetching SharedCount data...")

        if not self.sharedcount_api_key:
            print(f"   ⚠️  SharedCount API key not configured")
            return {'share_count': 0, 'comment_count': 0, 'reaction_count': 0}, 0, 0

        try:
            response = requests.get(
                'https://api.sharedcount.com/v1.0/',
                params={'url': url, 'apikey': self.sharedcount_api_key},
                timeout=30
            )

            if response.status_code != 200:
                print(f"   ⚠️  SharedCount API returned status {response.status_code}")
                raise Exception(f"SharedCount API error: {response.status_code}")

            data = response.json()

            # Extract metrics with defaults
            reddit_count = data.get('Reddit', 0) or 0
            facebook_data = {
                'share_count': data.get('Facebook', {}).get('share_count', 0) or 0,
                'comment_count': data.get('Facebook', {}).get('comment_count', 0) or 0,
                'reaction_count': data.get('Facebook', {}).get('reaction_count', 0) or 0
            }
            pinterest_count = data.get('Pinterest', 0) or 0

            print(f"   ✅ SharedCount data received")
            print(f"      Reddit: {reddit_count}, Pinterest: {pinterest_count}")
            print(f"      Facebook - Shares: {facebook_data['share_count']}, "
                  f"Comments: {facebook_data['comment_count']}, "
                  f"Reactions: {facebook_data['reaction_count']}")

            return facebook_data, reddit_count, pinterest_count

        except Exception as e:
            print(f"   ⚠️  SharedCount API error: {e}")
            return {'share_count': 0, 'comment_count': 0, 'reaction_count': 0}, 0, 0

    def get_x_data(self, url):
        """Get X (Twitter) engagement data"""
        print(f"   🐦 Fetching X (Twitter) data...")

        if not self.twitter_api_key:
            print(f"   ⚠️  Twitter API key not configured")
            return {
                'tweets': 0,
                'bookmarks': 0,
                'favorites': 0,
                'quotes': 0,
                'replies': 0,
                'retweets': 0
            }

        try:
            encoded_query = urllib.parse.quote(url)

            conn = http.client.HTTPSConnection("twitter-api45.p.rapidapi.com")
            headers = {
                'x-rapidapi-key': self.twitter_api_key,
                'x-rapidapi-host': "twitter-api45.p.rapidapi.com"
            }

            conn.request("GET", f"/search.php?query={encoded_query}", headers=headers)

            res = conn.getresponse()
            data = res.read()
            response_json = json.loads(data.decode("utf-8"))

            # Initialize counters
            x_data = {
                'tweets': 0,
                'bookmarks': 0,
                'favorites': 0,
                'quotes': 0,
                'replies': 0,
                'retweets': 0
            }

            # Loop through tweets
            for tweet in response_json.get("timeline", []):
                if tweet.get("type") != "tweet":
                    continue

                x_data['tweets'] += 1
                x_data['bookmarks'] += tweet.get("bookmarks", 0)
                x_data['favorites'] += tweet.get("favorites", 0)
                x_data['quotes'] += tweet.get("quotes", 0)
                x_data['replies'] += tweet.get("replies", 0)
                x_data['retweets'] += tweet.get("retweets", 0)

            print(f"   ✅ X data received")
            print(f"      Tweets: {x_data['tweets']}, Bookmarks: {x_data['bookmarks']}, "
                  f"Favorites: {x_data['favorites']}")
            print(f"      Quotes: {x_data['quotes']}, Replies: {x_data['replies']}, "
                  f"Retweets: {x_data['retweets']}")

            return x_data

        except Exception as e:
            print(f"   ⚠️  X (Twitter) API error: {e}")
            return {
                'tweets': 0,
                'bookmarks': 0,
                'favorites': 0,
                'quotes': 0,
                'replies': 0,
                'retweets': 0
            }

    def save_social_data(self, coverage_id, x_data, facebook_data, reddit_count,
                         pinterest_count, total_engagement, update_existing=False):
        """Save social data to database"""
        print(f"   💾 Saving social data to database...")

        conn = connect_db()
        cur = conn.cursor()

        try:
            if update_existing:
                # Update existing record
                cur.execute("""
                    UPDATE agentcy_client_coverage_social_shares
                    SET 
                        x_tweet_count = %s,
                        x_bookmark_count = %s,
                        x_favorite_count = %s,
                        x_quote_count = %s,
                        x_reply_count = %s,
                        x_retweet_count = %s,
                        reddit_count = %s,
                        facebook_share_count = %s,
                        facebook_comment_count = %s,
                        facebook_reaction_count = %s,
                        pinterest_count = %s,
                        total_social_engagement_count = %s,
                        updated_at = NOW()
                    WHERE coverage_id = %s
                """, (
                    x_data['tweets'],
                    x_data['bookmarks'],
                    x_data['favorites'],
                    x_data['quotes'],
                    x_data['replies'],
                    x_data['retweets'],
                    reddit_count,
                    facebook_data['share_count'],
                    facebook_data['comment_count'],
                    facebook_data['reaction_count'],
                    pinterest_count,
                    total_engagement,
                    coverage_id
                ))
            else:
                # Insert new record
                cur.execute("""
                    INSERT INTO agentcy_client_coverage_social_shares (
                        coverage_id,
                        x_tweet_count,
                        x_bookmark_count,
                        x_favorite_count,
                        x_quote_count,
                        x_reply_count,
                        x_retweet_count,
                        reddit_count,
                        facebook_share_count,
                        facebook_comment_count,
                        facebook_reaction_count,
                        pinterest_count,
                        total_social_engagement_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    coverage_id,
                    x_data['tweets'],
                    x_data['bookmarks'],
                    x_data['favorites'],
                    x_data['quotes'],
                    x_data['replies'],
                    x_data['retweets'],
                    reddit_count,
                    facebook_data['share_count'],
                    facebook_data['comment_count'],
                    facebook_data['reaction_count'],
                    pinterest_count,
                    total_engagement
                ))

            conn.commit()
            return True

        except Exception as e:
            print(f"   ❌ Database error: {e}")
            conn.rollback()
            return False
        finally:
            cur.close()
            conn.close()

    def show_summary(self, start_time):
        """Display final summary"""
        end_time = datetime.now()
        duration = end_time - start_time

        print(f"\n{'=' * 60}")
        print(f"📊 Update Complete!")
        print(f"{'=' * 60}")
        print(f"   Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Duration: {duration}")
        print(f"\n   Total processed: {self.processed}")
        print(f"   ✅ Updated: {self.updated}")
        print(f"   🆕 New records: {self.new_records}")
        print(f"   ⏸️  Unchanged: {self.unchanged}")
        print(f"   ❌ Failed: {self.failed}")

        # Show success rate
        if self.processed > 0:
            success_rate = ((self.updated + self.new_records) / self.processed) * 100
            print(f"\n   Success rate: {success_rate:.1f}%")

        print(f"{'=' * 60}\n")

    def show_trending_coverage(self, limit=10):
        """Show coverage with biggest engagement increase"""
        print(f"\n📈 Top {limit} Trending Coverage (by engagement increase)")
        print("=" * 100)

        conn = connect_db()
        cur = conn.cursor()

        try:
            # Get coverage from past N days with engagement changes
            cutoff_date = datetime.now() - timedelta(days=self.days_back)

            cur.execute("""
                WITH engagement_changes AS (
                    SELECT 
                        cl.id,
                        cl.client,
                        cl.title,
                        cl.published,
                        ss.total_social_engagement_count as current_engagement,
                        LAG(ss.total_social_engagement_count) OVER (
                            PARTITION BY cl.id 
                            ORDER BY ss.updated_at
                        ) as previous_engagement
                    FROM agentcy_client_coverage_log cl
                    JOIN agentcy_client_coverage_social_shares ss ON cl.id = ss.coverage_id
                    WHERE cl.published >= %s
                    AND cl.deleted = false
                )
                SELECT 
                    id,
                    client,
                    title,
                    published,
                    current_engagement,
                    COALESCE(current_engagement - previous_engagement, current_engagement) as increase
                FROM engagement_changes
                WHERE current_engagement > 0
                ORDER BY increase DESC
                LIMIT %s
            """, (cutoff_date, limit))

            results = cur.fetchall()

            print(f"{'ID':>6} {'Client':<20} {'Title':<45} {'Published':<10} {'Total':>8} {'Increase':>8}")
            print("-" * 100)

            for row in results:
                cov_id, client, title, published, total, increase = row
                title_short = title[:42] + '...' if len(title) > 45 else title
                client_short = client[:17] + '...' if len(client) > 20 else client
                pub_date = published.strftime('%Y-%m-%d') if published else 'N/A'

                print(f"{cov_id:>6} {client_short:<20} {title_short:<45} {pub_date:<10} "
                      f"{total:>8,} {increase:>+8,}")

        except Exception as e:
            print(f"❌ Error fetching trending coverage: {e}")
        finally:
            cur.close()
            conn.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Update social media metrics for recent press coverage",
        epilog="""
This script is designed to run twice daily via cron to keep social engagement
metrics current for recent press coverage.

Example cron entries:
  # Run at 8 AM and 8 PM daily
  0 8,20 * * * /usr/bin/python3 /path/to/update_recent_social_shares.py

  # Run every 12 hours
  0 */12 * * * /usr/bin/python3 /path/to/update_recent_social_shares.py --days 7
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--days",
        type=int,
        default=10,
        help="Look back N days for coverage to update (default: 10)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )
    parser.add_argument(
        "--show-trending",
        action="store_true",
        help="Show trending coverage after update"
    )

    args = parser.parse_args()

    # Validate environment
    if not DATABASE_URL:
        print("❌ Error: DATABASE_URL environment variable not set")
        sys.exit(1)

    # Create and run updater
    updater = RecentSocialSharesUpdater(
        days_back=args.days,
        dry_run=args.dry_run
    )

    try:
        updater.run()

        if args.show_trending and not args.dry_run:
            updater.show_trending_coverage()

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        updater.show_summary(datetime.now())
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()