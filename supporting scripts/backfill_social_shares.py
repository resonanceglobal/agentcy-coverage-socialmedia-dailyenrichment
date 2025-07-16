#!/usr/bin/env python3
"""
Backfill Social Shares Script
Fetches social media engagement metrics for existing coverage records

Usage:
    python backfill_social_shares.py [--limit N] [--client CLIENT_ID] [--ids ID1 ID2 ID3...]

Options:
    --limit N         Process only N records (default: 10)
    --client ID       Process only records for specific client ID
    --ids             Specific coverage IDs to process
"""

import argparse
import sys
import os
import time
import requests
import http.client
import urllib.parse
import json
from datetime import datetime
from collections import defaultdict

# Add parent directory to path to import project modules
sys.path.append('../')
from config.database import connect_db


class SocialSharesBackfiller:
    def __init__(self, limit=10, client_id=None, coverage_ids=None):
        self.limit = limit
        self.client_id = client_id
        self.coverage_ids = coverage_ids
        self.processed = 0
        self.succeeded = 0
        self.failed = 0
        self.skipped = 0

        # API Keys
        self.sharedcount_api_key = os.environ.get("SHAREDCOUNT_API_KEY", "c6d646fe157ec581c6be340efe64ddc1da90a729")
        self.twitter_api_key = os.environ.get("TWITTER_API_KEY", "eee06f1a70msh557ec3461344c08p1221adjsn1edc35b871d6")

    def run(self):
        """Main execution method"""
        print(f"🚀 Starting Social Shares Backfill")
        print(f"{'=' * 60}")

        if self.coverage_ids:
            print(f"Coverage IDs: {', '.join(map(str, self.coverage_ids))}")
        else:
            print(f"Limit: {self.limit} records")
            if self.client_id:
                print(f"Client ID filter: {self.client_id}")

        print(f"SharedCount API Key: {'✅ Configured' if self.sharedcount_api_key else '❌ Missing'}")
        print(f"Twitter API Key: {'✅ Configured' if self.twitter_api_key else '❌ Missing'}")
        print(f"{'=' * 60}\n")

        # Get records to process
        records = self.get_records_to_process()

        if not records:
            print("✅ No records found that need social shares data")
            return

        print(f"📋 Found {len(records)} records to process\n")

        # Process each record
        for record in records:
            self.process_record(record)

            # Rate limiting between requests
            if self.processed < len(records):
                time.sleep(1)  # 1 second between requests

        # Show summary
        self.show_summary()

    def get_records_to_process(self):
        """Get coverage records that don't have social shares data yet"""
        if self.coverage_ids:
            print(f"🔍 Fetching specific coverage records: {', '.join(map(str, self.coverage_ids))}...")
        else:
            print("🔍 Querying database for records needing social shares data...")

        conn = connect_db()
        cur = conn.cursor()

        try:
            if self.coverage_ids:
                # Query for specific coverage IDs
                placeholders = ','.join(['%s'] * len(self.coverage_ids))
                query = f"""
                    SELECT 
                        cl.id,
                        cl.client,
                        cl.client_id,
                        cl.title,
                        cl.url,
                        cl.created_at,
                        ss.coverage_id as has_social_data
                    FROM agentcy_client_coverage_log cl
                    LEFT JOIN agentcy_client_coverage_social_shares ss ON cl.id = ss.coverage_id
                    WHERE cl.id IN ({placeholders})
                    AND cl.url IS NOT NULL
                    AND cl.deleted = false
                    ORDER BY cl.id
                """
                cur.execute(query, self.coverage_ids)
            else:
                # Query for records without social shares data
                query = """
                    SELECT 
                        cl.id,
                        cl.client,
                        cl.client_id,
                        cl.title,
                        cl.url,
                        cl.created_at,
                        NULL as has_social_data
                    FROM agentcy_client_coverage_log cl
                    LEFT JOIN agentcy_client_coverage_social_shares ss ON cl.id = ss.coverage_id
                    WHERE ss.coverage_id IS NULL
                    AND cl.url IS NOT NULL
                    AND cl.deleted = false
                """

                params = []

                if self.client_id:
                    query += " AND cl.client_id = %s"
                    params.append(self.client_id)

                query += " ORDER BY cl.created_at DESC LIMIT %s"
                params.append(self.limit)

                cur.execute(query, params)

            records = []
            for row in cur.fetchall():
                records.append({
                    'id': row[0],
                    'client': row[1],
                    'client_id': row[2],
                    'title': row[3],
                    'url': row[4],
                    'created_at': row[5],
                    'has_social_data': row[6] is not None
                })

            # If specific IDs were requested, check which ones weren't found
            if self.coverage_ids:
                found_ids = [r['id'] for r in records]
                missing_ids = [cid for cid in self.coverage_ids if cid not in found_ids]
                if missing_ids:
                    print(f"⚠️  Coverage IDs not found or missing URL: {', '.join(map(str, missing_ids))}")

            return records

        except Exception as e:
            print(f"❌ Database query error: {e}")
            return []
        finally:
            cur.close()
            conn.close()

    def process_record(self, record):
        """Process a single coverage record"""
        self.processed += 1

        total = len(self.coverage_ids) if self.coverage_ids else self.limit
        print(f"\n🔄 Processing {self.processed}/{total}")
        print(f"   ID: {record['id']}")
        print(f"   Client: {record['client']} (ID: {record['client_id']})")
        print(f"   Title: {record['title'][:80]}...")
        print(f"   URL: {record['url']}")
        print(f"   Created: {record['created_at']}")

        if record['has_social_data']:
            print(f"   ⚠️  Already has social data - updating")

        try:
            # Get Facebook, Reddit, Pinterest data
            facebook_data, reddit_count, pinterest_count = self.get_sharedcount_data(record['url'])

            # Get X (Twitter) data
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
                print(f"   ✅ Social data saved successfully")
                print(f"   📊 Total engagement: {total_engagement:,}")
                self.succeeded += 1
            else:
                print(f"   ❌ Failed to save social data")
                self.failed += 1

        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            self.failed += 1

    def get_sharedcount_data(self, url):
        """Get social share data from SharedCount API"""
        print(f"   📱 Fetching SharedCount data...")

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
            # Return zeros on error
            return {'share_count': 0, 'comment_count': 0, 'reaction_count': 0}, 0, 0

    def get_x_data(self, url):
        """Get X (Twitter) engagement data"""
        print(f"   🐦 Fetching X (Twitter) data...")

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
            # Return zeros on error
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

    def show_summary(self):
        """Display final summary"""
        print(f"\n{'=' * 60}")
        print(f"📊 Backfill Complete!")
        print(f"{'=' * 60}")
        print(f"   Total processed: {self.processed}")
        print(f"   ✅ Succeeded: {self.succeeded}")
        print(f"   ⚠️  Skipped: {self.skipped}")
        print(f"   ❌ Failed: {self.failed}")

        # Show success rate
        if self.processed > 0:
            success_rate = (self.succeeded / self.processed) * 100
            print(f"\n   Success rate: {success_rate:.1f}%")

        print(f"{'=' * 60}\n")

    def show_top_engagement(self, limit=10):
        """Show top coverage by social engagement"""
        print(f"\n🏆 Top {limit} Coverage by Social Engagement")
        print("=" * 80)

        conn = connect_db()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT 
                    cl.id,
                    cl.client,
                    cl.title,
                    ss.total_social_engagement_count,
                    ss.x_tweet_count,
                    ss.facebook_share_count,
                    ss.reddit_count
                FROM agentcy_client_coverage_log cl
                JOIN agentcy_client_coverage_social_shares ss ON cl.id = ss.coverage_id
                ORDER BY ss.total_social_engagement_count DESC
                LIMIT %s
            """, (limit,))

            results = cur.fetchall()

            print(f"{'ID':>6} {'Client':<20} {'Title':<40} {'Total':>8} {'Tweets':>7} {'FB':>5} {'Reddit':>7}")
            print("-" * 80)

            for row in results:
                cov_id, client, title, total, tweets, fb, reddit = row
                title_short = title[:37] + '...' if len(title) > 40 else title
                client_short = client[:17] + '...' if len(client) > 20 else client

                print(f"{cov_id:>6} {client_short:<20} {title_short:<40} "
                      f"{total:>8,} {tweets:>7} {fb:>5} {reddit:>7}")

        except Exception as e:
            print(f"❌ Error fetching top engagement: {e}")
        finally:
            cur.close()
            conn.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Backfill social media engagement metrics for coverage records",
        epilog="""
Examples:
  # Process specific coverage IDs
  python backfill_social_shares.py --ids 12345 67890 11111

  # Process 10 most recent records
  python backfill_social_shares.py --limit 10

  # Process records for specific client
  python backfill_social_shares.py --client 123 --limit 50

  # Show top engagement after processing
  python backfill_social_shares.py --ids 12345 --show-top
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of records to process (default: 10, ignored if --ids is used)"
    )
    parser.add_argument(
        "--client",
        type=int,
        help="Process only records for specific client ID"
    )
    parser.add_argument(
        "--ids",
        nargs='+',
        type=int,
        help="Specific coverage IDs to process"
    )
    parser.add_argument(
        "--show-top",
        action="store_true",
        help="Show top engagement coverage after processing"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.ids and args.client:
        print("⚠️  WARNING: --client filter is ignored when using --ids")

    if args.ids and args.limit != 10:
        print("⚠️  WARNING: --limit is ignored when using --ids")

    # Create and run backfiller
    backfiller = SocialSharesBackfiller(
        limit=args.limit,
        client_id=args.client if not args.ids else None,
        coverage_ids=args.ids
    )

    try:
        backfiller.run()

        if args.show_top:
            backfiller.show_top_engagement()

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        backfiller.show_summary()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()