import requests
from dotenv import load_dotenv
import os

load_dotenv()

access_token = os.getenv('REDDIT_ACCESS_TOKEN')

headers = {
    'Authorization': f'bearer {access_token}',
    'User-Agent': 'MyAPI/0.0.1'
}

# Subreddits of interest.
subreddits = [
    'artificialintelligence', 'machinelearning', 'indiehacking',
]

# Function to fetch top 3 comments from a post
def fetch_top_comments(post_id):
    url = f'https://oauth.reddit.com/comments/{post_id}'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        post_data = response.json()
        comments = post_data[1]['data']['children']
        top_comments = [comment['data']['body'] for comment in comments[:1]]  # Get top 3 comments
        return top_comments
    else:
        return []

def grab_articles(topic):
  data = []
  print("Topic: ", topic)
  for subreddit in subreddits:
      # Search for the topic within each subreddit. Increase limit to get more posts.
      search_url = f'https://oauth.reddit.com/r/{subreddit}/search?q={topic}&restrict_sr=on&sort=hot&limit=1'
      res = requests.get(search_url, headers=headers)

      if res.status_code == 200:
          posts_data = res.json()['data']['children']

          for post in posts_data:
              post_data = post['data']
              post_id = post_data['id']
              title = post_data['title']
              selftext = post_data['selftext']
              top_comments = fetch_top_comments(post_id)
              data.append({
                  'subreddit': subreddit,
                  'title': title,
                  'post_content': selftext,
                  'top_comments': top_comments
              })
      else:
          print(f"Failed to fetch data from {subreddit}")
          
  # Example output
  print(data)
  return data
