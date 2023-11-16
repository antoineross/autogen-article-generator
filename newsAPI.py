import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = 'NEWSAPI_API_KEY'

# Functions -------------------------------------------------------------------------------------------------------------> 
def extract_article_info_from_list(article_list):   
    try:
        # Initialize a string to store the extracted information
        extracted_info = ""

        # Extract and store the desired information for each article
        for article in article_list:
            description = article.get("description", "N/A")
            title = article.get("title", "N/A")
            author = article.get("author", "N/A")
            content = article.get("content", "N/A")

            # Append the information to the string
            extracted_info += f"Title: {title}\nAuthor: {author}\nDescription: {description}\nContent: {content}\n\n"

        return extracted_info

    except Exception as e:
        # Handle any exceptions
        return f"An error occurred: {str(e)}"
      
def grab_articles(url, **kwargs):
    response = requests.get(url, 5)
    
    if response.status_code == 200:
        extracted_article = extract_article_info_from_list(response.json()['articles'])
        print(extracted_article)
        return extracted_article
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")

# URL Configuration Here -------------------------------------------------------------------------------------------------------------> 

BASE_URL_EVERYTHING = 'https://newsapi.org/v2/everything?'
BASE_URL_TOP_HEADLINES = 'https://newsapi.org/v2/top-headlines?'
TOPIC = 'bitcoin'
FROM = '2023-01-08' # Starting date
TO = '2023-11-08' # Ending date
SORTBY = 'popularity' # Relevancy, Popularity, PublishedAt
DOMAINS = 'techcrunch.com, thenextweb.com' # Domains you want to use. 
COUNTRY = 'gb&' # Options: US, AU, JP, PH etc. 
SOURCES = 'bbc-news' 
CATEGORY = 'business' # Options: business, entertainment, general health, science, sports, technology

# Everything URL list
urls_everything = f"{BASE_URL_EVERYTHING}q={TOPIC}&domains={DOMAINS}&sortBy={SORTBY}&apiKey={API_KEY}" 

# Top Headlines URL list
urls_top_headlines = f"{BASE_URL_TOP_HEADLINES}topic={TOPIC}&country={COUNTRY}&category={CATEGORY}&sources={SOURCES}&apiKey={API_KEY}"
