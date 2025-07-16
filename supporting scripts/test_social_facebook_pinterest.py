import requests

API_KEY = 'c6d646fe157ec581c6be340efe64ddc1da90a729'
url_to_check = 'https://www.zdnet.com/article/generative-ai-is-now-an-must-have-tool-for-technology-professionals'

response = requests.get(
    'https://api.sharedcount.com/v1.0/',
    params={'url': url_to_check, 'apikey': API_KEY}
)

data = response.json()

# Extract metrics with default 0 if missing
reddit_count = data.get('Reddit') or 0
facebook_share_count = data.get('Facebook', {}).get('share_count', 0)
facebook_comment_count = data.get('Facebook', {}).get('comment_count', 0)
facebook_reaction_count = data.get('Facebook', {}).get('reaction_count', 0)
pinterest_count = data.get('Pinterest') or 0

# Print results line by line
print(f"reddit_count: {reddit_count}")
print(f"facebook_share_count: {facebook_share_count}")
print(f"facebook_comment_count: {facebook_comment_count}")
print(f"facebook_reaction_count: {facebook_reaction_count}")
print(f"pinterest_count: {pinterest_count}")
