import http.client
import urllib.parse
import json
from collections import defaultdict

# Define the URL you want to search
search_url = "https://www.zdnet.com/article/generative-ai-is-now-an-must-have-tool-for-technology-professionals"
encoded_query = urllib.parse.quote(search_url)

# Set up the HTTPS connection
conn = http.client.HTTPSConnection("twitter-api45.p.rapidapi.com")

# Set the headers with your API key
headers = {
    'x-rapidapi-key': "eee06f1a70msh557ec3461344c08p1221adjsn1edc35b871d6",
    'x-rapidapi-host': "twitter-api45.p.rapidapi.com"
}

# Make the GET request using the encoded URL in the query
conn.request("GET", f"/search.php?query={encoded_query}", headers=headers)

# Read and decode the response
res = conn.getresponse()
data = res.read()
response_json = json.loads(data.decode("utf-8"))

# Track metrics by screen_name
user_metrics = defaultdict(lambda: {
    "tweets": 0,
    "bookmarks": 0,
    "favorites": 0,
    "quotes": 0,
    "replies": 0,
    "retweets": 0
})

# Global counters
total_tweets = 0
total_bookmarks = 0
total_favorites = 0
total_quotes = 0
total_replies = 0
total_retweets = 0

# Loop through tweets
for tweet in response_json.get("timeline", []):
    if tweet.get("type") != "tweet":
        continue

    screen_name = tweet.get("screen_name", "unknown")

    bookmarks = tweet.get("bookmarks", 0)
    favorites = tweet.get("favorites", 0)
    quotes = tweet.get("quotes", 0)
    replies = tweet.get("replies", 0)
    retweets = tweet.get("retweets", 0)

    user_metrics[screen_name]["tweets"] += 1
    user_metrics[screen_name]["bookmarks"] += bookmarks
    user_metrics[screen_name]["favorites"] += favorites
    user_metrics[screen_name]["quotes"] += quotes
    user_metrics[screen_name]["replies"] += replies
    user_metrics[screen_name]["retweets"] += retweets

    total_tweets += 1
    total_bookmarks += bookmarks
    total_favorites += favorites
    total_quotes += quotes
    total_replies += replies
    total_retweets += retweets

# Output metrics per user
print("📊 Metrics by handle:\n")
for handle, metrics in user_metrics.items():
    print(f"{handle}: tweets={metrics['tweets']}, bookmarks={metrics['bookmarks']}, "
          f"favorites={metrics['favorites']}, quotes={metrics['quotes']}, "
          f"replies={metrics['replies']}, retweets={metrics['retweets']}")

# Output totals
print("\n📈 Total metrics across all users:")
print(f"Total tweets: {total_tweets}")
print(f"Total bookmarks: {total_bookmarks}")
print(f"Total favorites: {total_favorites}")
print(f"Total quotes: {total_quotes}")
print(f"Total replies: {total_replies}")
print(f"Total retweets: {total_retweets}")

# Everything today score
everything_today = (
    total_tweets +
    total_bookmarks +
    total_favorites +
    total_quotes +
    total_replies +
    total_retweets
)

print(f"\n🧮 Everything today score: {everything_today}")
